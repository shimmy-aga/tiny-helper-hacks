import os

def replace_in_filenames(old_text, new_text):
    folder_path = os.path.dirname(os.path.abspath(__file__))  # folder where script is located

    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)

        # Skip directories
        if os.path.isdir(file_path):
            continue

        # Skip the script itself
        if filename == os.path.basename(__file__):
            continue

        # If no old_text is provided, prepend new_text
        if old_text == "":
            new_filename = new_text + filename
        # Otherwise, replace normally
        elif old_text in filename:
            new_filename = filename.replace(old_text, new_text)
        else:
            continue  # skip if nothing to replace

        new_file_path = os.path.join(folder_path, new_filename)
        os.rename(file_path, new_file_path)
        print(f"Renamed: {filename} -> {new_filename}")

if __name__ == "__main__":
    old = input("Enter the text to replace (leave empty to prepend): ").strip()
    new = input("Enter the replacement text: ").strip()
    replace_in_filenames(old, new)
