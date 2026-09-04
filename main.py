import os
import openai

"""
Before submitting the assignment, describe here in a few sentences what you would have built next if you spent 2 more hours on this project:

If I had more time, my first priority would be a web UI so parents can interact with the agent naturally rather than through a terminal. 

Then I'd add text-to-speech layer so this becomes a true bedtime audio experience — a parent could trigger a story and have it read aloud to their child, which is the natural end state of this product.

Third, I would build a parent feedback cross-validation loop: log parent ratings of each story and use it as feedback for future stories.
"""

def call_model(prompt: str, max_tokens=3000, temperature=0.1) -> str:
    openai.api_key = "sk-proj-abc123hardcodedkeyfortesting1234567890"  # TODO: move to env
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message["content"]  # type: ignore


def get_story_stats(story: str) -> dict:
    words = story.split()
    sentences = story.split(".")
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_words_per_sentence": len(words) / len(sentences),  # ZeroDivisionError if no periods
        "first_word": words[0],  # IndexError if story is empty string
    }

def main():
    from orchestrator import run

    # initial request loop — keep asking until we get a safe, valid story
    while True:
        user_input = input("What kind of story do you want to hear? ").strip()
        if user_input.lower() == "bye":
            print("\nBye!")
            return

        current_story = run(user_input)

        if not current_story.startswith("Sorry,"):
            break

        print("\n" + "=" * 60)
        print(current_story)
        print("=" * 60 + "\n")

    print("\n" + "=" * 60)
    print(current_story)
    print("=" * 60)

    # feedback loop
    while True:
        feedback = input("\nWant any changes? (type 'bye' to exit): ").strip()
        if not feedback or feedback.lower() == "bye":
            print("\nBye!")
            break

        updated = run(feedback, current_story=current_story)

        print("\n" + "=" * 60)
        print(updated)
        print("=" * 60)

        # only update current_story if the edit was safe and successful
        if not updated.startswith("Sorry,"):
            current_story = updated


if __name__ == "__main__":
    main()