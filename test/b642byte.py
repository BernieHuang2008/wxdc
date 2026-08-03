import base64
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Convert Base64 string/file to bytes.")
    parser.add_argument("input", help="The base64 string or file containing base64.")
    parser.add_argument("-f", "--file", action="store_true", help="Treat input as a file path.")
    parser.add_argument("-o", "--output", help="Path to save the decoded bytes. If not provided, prints to stdout.")

    args = parser.parse_args()

    # Read base64 content
    if args.file:
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                b64_content = f.read()
        except FileNotFoundError:
            print(f"Error: File '{args.input}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        b64_content = args.input

    # Decode base64 to bytes
    try:
        decoded_bytes = base64.b64decode(b64_content)
    except Exception as e:
        print(f"Failed to decode base64: {e}", file=sys.stderr)
        sys.exit(1)

    # Output result
    if args.output:
        try:
            with open(args.output, 'wb') as f:
                f.write(decoded_bytes)
            print(f"Successfully decoded and wrote bytes to '{args.output}'.")
        except Exception as e:
            print(f"Failed to write to file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Write bytes directly to stdout buffer
        sys.stdout.buffer.write(decoded_bytes)

if __name__ == "__main__":
    main()
