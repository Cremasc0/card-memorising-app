"""Lightly denoise reviewed card crops for cleaner color image tracing."""

import os

import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "Trevisane Crops")
OUTPUT_DIR = os.path.join(BASE_DIR, "work", "vector-input")
SUITS = ["Bastoni", "Coppa", "Dinari", "Spada"]


def main():
    for suit in SUITS:
        source_dir = os.path.join(INPUT_DIR, suit)
        output_dir = os.path.join(OUTPUT_DIR, suit)
        os.makedirs(output_dir, exist_ok=True)
        for card in range(1, 11):
            name = f"{suit}_{card:02d}.png"
            source_path = os.path.join(source_dir, name)
            source = cv2.imread(source_path, cv2.IMREAD_COLOR)
            if source is None:
                raise FileNotFoundError(source_path)
            denoised = cv2.bilateralFilter(source, 9, 35, 5)
            cv2.imwrite(
                os.path.join(output_dir, name),
                denoised,
                [cv2.IMWRITE_PNG_COMPRESSION, 3],
            )
    print(f"Prepared 40 denoised trace inputs in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
