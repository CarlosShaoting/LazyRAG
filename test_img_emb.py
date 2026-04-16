from pathlib import Path

from chat.utils.load_config import get_retrieval_settings
from chat.pipelines.builders.get_models import get_automodel
from parsing.image_reader import ImageReader

img = Path("/home/mnt/cuishaoting/LazyRAG/test_doc/大象.jpg")

settings = get_retrieval_settings()
embed = {k: get_automodel(k) for k in settings.embed_keys}

image_embed_key = settings.embed_keys[-1] if settings.embed_keys else None
reader = ImageReader(
    embed_key=image_embed_key,
    embed_model=embed.get(image_embed_key) if image_embed_key else None,
)

nodes = reader._load_data(img)
node = nodes[0]

print("embed_keys:", settings.embed_keys)
print("image_embed_key:", image_embed_key)
print("node type:", type(node).__name__)
print("node embedding keys:", list(node.embedding.keys()))
if image_embed_key in node.embedding:
    print("embedding dim:", len(node.embedding[image_embed_key]))
    print("embedding first3:", node.embedding[image_embed_key][:3])
print("metadata img_emb keys:", list((node.metadata.get("img_emb") or {}).keys()))

# export PYTHONPATH=/home/mnt/cuishaoting/LazyLLM:/home/mnt/cuishaoting/LazyRAG:/home/mnt/cuishaoting/LazyRAG/algorithm
# export LAZYRAG_MODEL_CONFIG_PATH=/home/mnt/cuishaoting/LazyRAG/algorithm/chat/runtime_models.inner.yaml
# python /home/mnt/cuishaoting/LazyRAG/test_img_emb.py