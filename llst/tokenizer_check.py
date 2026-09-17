import sys, os, hashlib, json
from transformers import AutoTokenizer

def verify_tokenizer(tok_path):
    tok = AutoTokenizer.from_pretrained(tok_path, trust_remote_code=True)
    report = {
        "tokenizer_class": tok.__class__.__name__,
        "vocab_size": getattr(tok, "vocab_size", None),
        "files": {}
    }
    for fname in os.listdir(tok_path):
        fpath = os.path.join(tok_path, fname)
        if os.path.isfile(fpath) and fname.endswith(".json"):
            with open(fpath, "rb") as f:
                report["files"][fname] = hashlib.sha256(f.read()).hexdigest()
    return report

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "./tokenizer"
    print(json.dumps(verify_tokenizer(p), indent=2))
