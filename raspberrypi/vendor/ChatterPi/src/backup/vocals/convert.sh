#!/bin/bash
for file in *.wav; do
    mv "$file" "${file%.wav}.original.wav"  # Rename original
    sox "${file%.wav}.original.wav" -b 16 -e signed-integer "$file" channels 1 rate 44100  # Convert and replace
done
echo "Conversion and replacement complete!"
