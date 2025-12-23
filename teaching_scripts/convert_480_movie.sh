#!/bin/bash

# Usage: ./convert_480_movie.sh input_movie.mov

# Check if input file is provided
if [ -z "$1" ]; then
  echo "Usage: $0 input_movie.mov"
  exit 1
fi

input_file="$1"
output_file="${input_file%.*}_converted.mp4"

ffmpeg -i "$input_file" \
  -vf "scale=-2:'min(1080,ih)'" \
  -fpsmax 30 \
  -c:v libx264 -crf 23 -preset medium -tune animation \
  -c:a aac -b:a 96k \
  -af "highpass=f=80, afftdn, loudnorm=I=-16:TP=-1.5:LRA=11" \
  -movflags +faststart \
  "$output_file"

echo "Conversion complete: $output_file"
