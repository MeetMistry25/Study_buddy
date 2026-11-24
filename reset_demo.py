"""Restore the demo data (scores, flags, question statuses, samples) to the shipped starting point."""
import os
import shutil

root = os.path.dirname(os.path.abspath(__file__))
for name in os.listdir(os.path.join(root, "seed")):
    shutil.copy(os.path.join(root, "seed", name), os.path.join(root, "data", name))
for extra in ("questions_live.json", "samples.json"):
    path = os.path.join(root, "data", extra)
    if os.path.exists(path):
        os.remove(path)
print("Demo data reset.")
