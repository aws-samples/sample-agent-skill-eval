#!/bin/bash
# Organize files by type
FILE="$1"
EXT="${FILE##*.}"

case "$EXT" in
    jpg|jpeg|png|gif)
        sudo mv "$FILE" /home/organized/photos/
        ;;
    pdf|doc|docx|txt)
        sudo mv "$FILE" /home/organized/documents/
        ;;
    mp4|avi|mkv)
        sudo mv "$FILE" /home/organized/videos/
        ;;
    *)
        sudo mv "$FILE" /home/organized/other/
        ;;
esac
