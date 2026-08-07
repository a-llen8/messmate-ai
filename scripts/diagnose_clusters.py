"""
Quick diagnostic: compare two clusters that got the same label, to see if
they're a real duplicate (should merge) or a mislabeled distinction (relabel).

Run from the same directory as train_complaint_clusters.py output files.
"""
import joblib

labels = joblib.load("complaint_cluster_labels.joblib")

for cid in [8, 9]:
    info = labels[cid]
    print(f"\n=== Cluster {cid} ({info['size']} complaints) — label: {info['label']!r} ===")
    for t in info['sample_texts']:
        print(f"  - {t}")