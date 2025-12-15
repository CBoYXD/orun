import ollama
from orun import db, utils
from orun.utils import Colors, colored, print_error

def handle_ollama_stream(stream) -> str:
    """Prints the stream and returns the full response."""
    full_response = ""
    try:
        for chunk in stream:
            content = chunk['message']['content']
            print(content, end='', flush=True)
            full_response += content
    except Exception as e:
        print() # Newline
        print_error(f"Stream Error: {e}")
    finally:
        print()
    return full_response

def run_single_shot(model_name: str, user_prompt: str, image_paths: list[str] | None):
    """Handles a single query to the model."""
    print(colored(f"🤖 [{model_name}] Thinking...", Colors.CYAN))

    conversation_id = db.create_conversation(model_name)
    db.add_message(conversation_id, "user", user_prompt, image_paths or None)

    try:
        stream = ollama.chat(
            model=model_name,
            messages=[{'role': 'user', 'content': user_prompt, 'images': image_paths or None}],
            stream=True,
        )
        response = handle_ollama_stream(stream)
        if response:
            db.add_message(conversation_id, "assistant", response)
    except Exception as e:
        print() # Newline
        print_error(f"Error: {e}")

def run_chat_mode(model_name: str, initial_prompt: str | None, initial_images: list[str] | None, conversation_id: int | None = None):
    """Runs an interactive chat session."""
    print(colored(f"Entering chat mode with '{model_name}'.", Colors.GREEN))
    print("Type 'quit' or 'exit' to end the session.")

    if conversation_id:
        messages = db.get_conversation_messages(conversation_id)
        print(colored(f"Loaded {len(messages)} messages from conversation #{conversation_id}", Colors.GREY))
    else:
        messages = []
        conversation_id = db.create_conversation(model_name)

    if initial_prompt or initial_images:
        if not initial_prompt:
            initial_prompt = "Describe this image."

        print(colored(f"🤖 [{model_name}] Thinking...", Colors.CYAN))
        print(colored("Assistant: ", Colors.BLUE), end="")

        user_message = {'role': 'user', 'content': initial_prompt, 'images': initial_images or None}
        messages.append(user_message)
        db.add_message(conversation_id, "user", initial_prompt, initial_images or None)

        try:
            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            assistant_response = handle_ollama_stream(stream)
            if assistant_response:
                messages.append({'role': 'assistant', 'content': assistant_response})
                db.add_message(conversation_id, "assistant", assistant_response)
        except Exception as e:
            print() # Newline
            print_error(f"Error: {e}")
            messages.pop()

    while True:
        try:
            user_input = input(colored("\nYou: ", Colors.GREEN))
            if user_input.lower() in ['quit', 'exit']:
                break

            print(colored(f"🤖 [{model_name}] Thinking...", Colors.CYAN))
            print(colored("Assistant: ", Colors.BLUE), end="")

            messages.append({'role': 'user', 'content': user_input})
            db.add_message(conversation_id, "user", user_input)

            stream = ollama.chat(model=model_name, messages=messages, stream=True)
            assistant_response = handle_ollama_stream(stream)
            if assistant_response:
                messages.append({'role': 'assistant', 'content': assistant_response})
                db.add_message(conversation_id, "assistant", assistant_response)
            else:
                messages.pop()

        except EOFError:
            break
        except KeyboardInterrupt:
            print(colored("\nChat session interrupted.", Colors.YELLOW))
            break
        except Exception as e:
            print() # Newline
            print_error(f"Error: {e}")
            if messages and messages[-1]['role'] == 'user':
                messages.pop()
