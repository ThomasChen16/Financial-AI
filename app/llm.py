# Combines the text from the chunks into a single context string that can be used by LLM to answer user"s question
import requests

# Takes in user question and chunk and calls the agent and retrieve the response for the user
def generate_answer(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join([c["text"] for c in chunks])
    
    # system message to send to LLM
    system_message = "You are an analyst. Answer using ONLY the context. If it isn't in the context, say so"
    
    # user message should contain context and the question
    user_message = f"Context: {context}\nQuestion: {question}"
    
    # message for Ollama
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]
    
    try:
        # request post to send HTTP request
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": "llama3.2:3b", "messages": messages, "stream": False},
            timeout=(10, 180)  # 10s to connect, 180s for the model to answer
        )
        # throws an exception if HTTP request fails
        response.raise_for_status()
        
        # return the message and content from the response dict
        return response.json()["message"]["content"]
    except requests.RequestException as exc:
        return f"Unable to generate an answer: {exc}"
    except (ValueError, KeyError, TypeError):
        return "Unable to generate an answer: invalid response from Ollama"
    