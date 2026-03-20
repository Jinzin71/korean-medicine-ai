import os
from huggingface_hub import HfApi

api = HfApi()
api.upload_folder(
    folder_path=".",
    repo_id="magicians7/korean-medicine-ai",
    repo_type="space",
    token=os.environ["HF_TOKEN"],
    ignore_patterns=[".git", ".github", "__pycache__", "*.pyc", ".gitignore"],
)
print("Upload complete!")
