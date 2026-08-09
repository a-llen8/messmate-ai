"""
MessMate — Week 7: Complaint Clustering (complaint analyzer)

Groups similar complaints together automatically, then asks Gemini to give
each group a short, human-readable label a caterer could scan at a glance
(e.g. "Cold food during breakfast", "Slow service at dinner rush").

This is CLUSTERING, not classification — the number of groups is discovered
from the data itself (via HDBSCAN), not chosen in advance. A complaint that
doesn't fit any group cleanly gets labeled "Uncategorized / one-off" (HDBSCAN
calls this "noise") rather than forced into the nearest cluster. Exact-duplicate
complaint text (common in the synthetic generator's templated output) is
deduplicated before clustering and broadcast back afterward — clustering the
same duplicate repeatedly wastes compute and can trip up HDBSCAN's density
estimate at the zero-distance singularity, sometimes splitting identical text
across different cluster IDs instead of merging it.

Different in kind from the other three models:
  - Week 6 (attendance): per-student classification, tuned threshold
  - Week 7 (churn):       per-student classification, tuned threshold
  - Week 7 (headcount):   regression, evaluated on MAE/RMSE
  - Week 7 (complaints):  unsupervised clustering, no train/test split,
                          no "accuracy" — evaluated by whether the groups
                          make sense to a human reading them

Embeddings are computed LOCALLY (sentence-transformers), not via the Gemini API.
The Gemini free tier caps text-embedding-001 at 1,000 items/day — a hard daily
quota, not a rate limit — which doesn't fit 1,369 complaints today and will keep
breaking as the complaint count grows. Local embeddings have no quota and no
network dependency. Gemini is still used, but only for cluster LABELING (a
handful of calls — one per cluster found, not one per complaint).

Usage:
    cd backend
    venv\\Scripts\\activate
    python ..\\scripts\\train_complaint_clusters.py

Requires the same DB the backend uses (reads DB_PASS + GEMINI_API_KEY from
project-root .env). Requires: pandas, numpy, sqlalchemy, psycopg2-binary,
hdbscan, sentence-transformers, google-genai, python-dotenv, joblib

    pip install hdbscan sentence-transformers umap-learn google-genai --break-system-packages
    (run once, in your venv — sentence-transformers is a ~500MB download the
    first time, since it pulls the embedding model weights)
"""

import os
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
import joblib

# ── Config ──────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # local sentence-transformers model, free, no quota
LABELING_MODEL = "gemini-3.1-flash-lite"
MIN_CLUSTER_SIZE = 10          # smallest group HDBSCAN will call a real cluster
MIN_SAMPLES = 3                 # lower = less conservative about merging nearby points into one cluster
SAMPLE_TEXTS_FOR_LABELING = 8  # how many example complaints Gemini sees per cluster

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "ml", "models")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_CLUSTERER_PATH = os.path.join(OUTPUT_DIR, "complaint_clusterer.joblib")
OUTPUT_REDUCER_PATH = os.path.join(OUTPUT_DIR, "complaint_umap_reducer.joblib")
OUTPUT_LABELS_PATH = os.path.join(OUTPUT_DIR, "complaint_cluster_labels.joblib")
OUTPUT_ASSIGNMENTS_PATH = "complaint_cluster_assignments.csv"


def load_complaints(engine):
    print("Loading complaints from the database...")
    complaints = pd.read_sql("""
        SELECT c.id, c.user_id, c.text, c.category, c.status, c.created_at
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE u.email LIKE 'synth%%'
        ORDER BY c.id
    """, engine)
    print(f"  Complaints: {complaints.shape}")
    if len(complaints) < 30:
        print("ERROR: too few complaints to cluster meaningfully (<30). "
              "Check the DB has synthetic complaint data.")
        sys.exit(1)
    return complaints


def embed_complaints(texts):
    from sentence_transformers import SentenceTransformer
    print(f"Loading local embedding model ({EMBEDDING_MODEL})... "
          f"(first run downloads the weights, ~90MB, then it's cached)")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"Embedding {len(texts)} complaints locally (no API calls, no quota)...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    return embeddings


def cluster_embeddings(embeddings):
    import hdbscan
    import umap

    # HDBSCAN is density-based, and density estimates fall apart in high
    # dimensions (the "curse of dimensionality" — in 384-dim space, almost
    # all points end up nearly equidistant from each other, so there's no
    # real density signal left to find clusters in). This is the standard
    # reason HDBSCAN reports "0 clusters, 100% noise" on raw sentence
    # embeddings even when the underlying text is clearly grouped — it's
    # the same reduce-then-cluster recipe BERTopic uses under the hood.
    print("Reducing embeddings to 5 dimensions with UMAP before clustering...")
    n_neighbors = min(8, max(2, len(embeddings) - 1))
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,  # smaller = UMAP preserves finer local structure
        n_components=5,           # instead of smoothing toward a few broad blobs
        min_dist=0.0,
        metric='cosine',       # cosine distance is the right notion of
        random_state=42,       # similarity for sentence embeddings
    )
    reduced_embeddings = reducer.fit_transform(embeddings)

    print(f"Clustering with HDBSCAN (min_cluster_size={MIN_CLUSTER_SIZE}, min_samples={MIN_SAMPLES})...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric='euclidean',    # euclidean on the UMAP-reduced space, not the raw embeddings
        # cluster_selection_method left at the default ('eom') — 'leaf' over-split one
        # real category (undercooked food) into two clusters with an identical label
        prediction_data=True,  # required to assign future complaints later via approximate_predict
    )
    cluster_ids = clusterer.fit_predict(reduced_embeddings)

    n_clusters = len(set(cluster_ids)) - (1 if -1 in cluster_ids else 0)
    n_noise = (cluster_ids == -1).sum()
    print(f"  Found {n_clusters} clusters, {n_noise} complaints unclustered "
          f"({n_noise / len(cluster_ids):.1%} — labeled 'Uncategorized / one-off')")
    return clusterer, reducer, cluster_ids


def label_clusters(client, complaints, cluster_ids):
    print("Asking Gemini to label each cluster...")
    complaints = complaints.copy()
    complaints['cluster_id'] = cluster_ids

    labels = {}
    for cid in sorted(set(cluster_ids)):
        members = complaints[complaints['cluster_id'] == cid]

        if cid == -1:
            labels[cid] = {
                'label': 'Uncategorized / one-off',
                'size': len(members),
                'sample_texts': members['text'].head(3).tolist(),
            }
            continue

        sample = members['text'].sample(
            min(SAMPLE_TEXTS_FOR_LABELING, len(members)), random_state=42
        ).tolist()
        prompt = (
            "These are real complaints from students about their college hostel mess "
            "(dining hall), all grouped together because they're similar:\n\n"
            + "\n".join(f"- {t}" for t in sample)
            + "\n\nWrite a short label (4-6 words) that a busy caterer could scan at a "
              "glance to understand what this group of complaints is about. "
              "No quotes, no punctuation at the end, just the label itself."
        )
        response = client.models.generate_content(model=LABELING_MODEL, contents=prompt)
        label_text = response.text.strip().strip('"').strip("'")

        labels[cid] = {
            'label': label_text,
            'size': len(members),
            'sample_texts': sample[:3],
        }
        print(f"  Cluster {cid} ({len(members)} complaints): {label_text}")

    return labels, complaints


def dedupe_texts(complaints):
    """Return (unique_texts, index_map) where index_map[i] gives the position
    in unique_texts for complaints.iloc[i]. Exact-duplicate complaint text is
    common in the synthetic generator's templated output, and clustering the
    same duplicates repeatedly both wastes compute and can trip up HDBSCAN —
    points at distance 0 sit at a singularity in its density estimate and can
    end up arbitrarily split across different cluster IDs instead of merging.
    Deduplicating first avoids that entirely and is strictly cheaper.
    """
    unique_texts = complaints['text'].drop_duplicates().tolist()
    text_to_unique_idx = {t: i for i, t in enumerate(unique_texts)}
    index_map = complaints['text'].map(text_to_unique_idx).to_numpy()
    n_dupes = len(complaints) - len(unique_texts)
    if n_dupes > 0:
        print(f"  {n_dupes} of {len(complaints)} complaints are exact-duplicate "
              f"text ({len(unique_texts)} unique) — clustering unique texts only, "
              f"then broadcasting assignments back to all rows.")
    return unique_texts, index_map


def main():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(env_path)
    db_pass = os.getenv("DB_PASS")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not db_pass:
        print("ERROR: DB_PASS not found in .env")
        sys.exit(1)
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not found in .env")
        sys.exit(1)

    database_url = f"postgresql://messmate:{db_pass}@localhost:5432/messmate"
    engine = create_engine(database_url)

    from google import genai
    client = genai.Client(api_key=gemini_key)

    complaints = load_complaints(engine)
    unique_texts, index_map = dedupe_texts(complaints)
    unique_embeddings = embed_complaints(unique_texts)
    clusterer, reducer, unique_cluster_ids = cluster_embeddings(unique_embeddings)
    cluster_ids = unique_cluster_ids[index_map]  # broadcast back to every row
    n_noise_total = (cluster_ids == -1).sum()
    print(f"  Broadcast to all {len(complaints)} complaints: "
          f"{n_noise_total} unclustered ({n_noise_total / len(complaints):.1%})")
    labels, complaints_with_clusters = label_clusters(client, complaints, cluster_ids)

    complaints_with_clusters['cluster_label'] = complaints_with_clusters['cluster_id'].map(
        lambda cid: labels[cid]['label']
    )

    print("\nCluster summary (largest first):")
    summary = (
        complaints_with_clusters.groupby(['cluster_id', 'cluster_label'])
        .size()
        .reset_index(name='count')
        .sort_values('count', ascending=False)
    )
    print(summary.to_string(index=False))

    joblib.dump(clusterer, OUTPUT_CLUSTERER_PATH)
    joblib.dump(reducer, OUTPUT_REDUCER_PATH)
    joblib.dump(labels, OUTPUT_LABELS_PATH)
    complaints_with_clusters.drop(columns=['text']).to_csv(OUTPUT_ASSIGNMENTS_PATH, index=False)
    # (text dropped from the CSV to avoid duplicating raw complaint content outside the DB;
    #  join back on complaint id if the full text is needed downstream)

    print(f"\nSaved: {OUTPUT_CLUSTERER_PATH}")
    print(f"Saved: {OUTPUT_REDUCER_PATH}")
    print(f"Saved: {OUTPUT_LABELS_PATH}")
    print(f"Saved: {OUTPUT_ASSIGNMENTS_PATH}")
    print("\nNote: to assign a NEW complaint to an existing cluster later without "
          "re-running this whole script: embed its text with the SAME local model "
          f"({EMBEDDING_MODEL}), reduce it with the saved UMAP reducer "
          f"({OUTPUT_REDUCER_PATH} — reducer.transform([embedding]), NOT fit_transform), "
          "then call hdbscan.approximate_predict(clusterer, [reduced_embedding]). "
          "Skipping the reducer step will silently give wrong cluster assignments, "
          "since the clusterer was fit on the reduced 5-dim space, not the raw embedding.")


if __name__ == "__main__":
    main()