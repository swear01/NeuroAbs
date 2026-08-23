import re


def get_signal(input_filename, output_filename, prefix):
    pattern = re.compile(
        rf"removing unused non-port wire (\\{re.escape(prefix)}"
        rf"(?:\.[A-Za-z_][A-Za-z0-9_$]*)+)\b"
    )
    with open(input_filename, 'r') as infile:
        signals = {
            match.group(1)
            for line in infile
            if (match := pattern.search(line))
        }

    with open(output_filename, 'w') as outfile:
        for signal in sorted(signals):
            outfile.write(signal + '\n')

    print(f"Processing complete. Results written to {output_filename}")

