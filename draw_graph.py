from agents.doc_retrieval import app

image_data = app.get_graph().draw_mermaid_png()

with open("doc_retrieval.png", "wb") as f:
    f.write(image_data)
        