def run(task_id, params, seed):
    """Stub runner for the launcher smoke test. Not a real experiment."""
    score = {"x": 0.90, "y": 0.91}.get(str(params.get("candidate", "")), 0.88)
    return {"metrics": {"roc_auc": score}}
