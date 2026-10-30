"""
Trevisane Card Cropper v5
============================
For each HEIC photo in Trevisane/{suit}/:
  1. Read HEIC via pillow-heif + EXIF rotate
  2. Coppa/Spada are landscape: rotate 90 deg CCW to portrait
  3. Detect the printed frame nearest the photo centre, filtering nested contours
  4. Find the centre card's printed rectangular frame and correct perspective
  5. Resize to 51x103mm @ 300 DPI = 602x1217 px
  6. Save crop-only PNGs to Trevisane Crops/{suit}/ for visual review
"""

import os
import numpy as np
import cv2
import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

# ---------------------------------------------------------------------------
DPI = 300
MM_PER_INCH = 25.4
CARD_W_MM, CARD_H_MM = 51, 103
CARD_W_PX = int(round(CARD_W_MM / MM_PER_INCH * DPI))   # 602
CARD_H_PX = int(round(CARD_H_MM / MM_PER_INCH * DPI))   # 1217
CARD_ASPECT = CARD_W_MM / CARD_H_MM                      # 0.495 (w/h portrait)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR  = os.path.join(BASE_DIR, "Trevisane")
OUTPUT_DIR = os.path.join(BASE_DIR, "Trevisane Crops")
SUITS      = ["Bastoni", "Coppa", "Dinari", "Spada"]

# Suits photographed in landscape orientation — rotate 90 CCW to portrait
LANDSCAPE_SUITS = {"Spada", "Coppa"}

SUIT_FILES = {
    "Bastoni": [f"IMG_{n}.HEIC" for n in range(5085, 5095)],
    "Spada":   [f"IMG_{n}.HEIC" for n in range(5095, 5105)],
    "Dinari":  [f"IMG_{n}.HEIC" for n in range(5105, 5115)],
    "Coppa":   [f"IMG_{n}.HEIC" for n in range(5115, 5125)],
}
CARD_NUMBERS = list(range(1, 11))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def order_corners(pts):
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    return np.array([
        pts[np.argmin(s)],   # tl
        pts[np.argmin(d)],   # tr
        pts[np.argmax(s)],   # br
        pts[np.argmax(d)],   # bl
    ], dtype=np.float32)


def side_lengths(corners):
    tl, tr, br, bl = corners
    w = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2.0
    h = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2.0
    return w, h


def rect_corners(x0, y0, x1, y1):
    return np.array([
        [x0, y0], [x1, y0],
        [x1, y1], [x0, y1],
    ], dtype=np.float32)


def is_card_aspect(w, h, tol=0.30):
    """True if w:h (or h:w) matches CARD_ASPECT within tolerance."""
    if w <= 0 or h <= 0:
        return False
    asp = min(w, h) / max(w, h)
    return abs(asp - CARD_ASPECT) < tol


# ---------------------------------------------------------------------------
# Binary threshold
# ---------------------------------------------------------------------------

def threshold_image(img_rgb):
    """Binary mask: white = card faces, black = background."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (9, 9), 0)
    _, thresh = cv2.threshold(blur, 180, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    return cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)


# ---------------------------------------------------------------------------
# Profile-based card splitting
# ---------------------------------------------------------------------------

def split_by_columns(closed_roi, n_estimate):
    """
    Split a binary ROI into n_estimate column slices, finding real gap positions.
    Returns list of x-split positions (within ROI).
    """
    bh, bw = closed_roi.shape[:2]
    if bw == 0 or bh == 0:
        return []

    col_density = closed_roi.sum(axis=0).astype(float) / (bh * 255.0)
    smooth = np.convolve(col_density, np.ones(11) / 11, mode='same')

    # Find local minima that are significantly below neighbours
    # We want exactly n_estimate-1 split points
    # Strategy: find all valleys, keep the n_estimate-1 deepest ones
    valley_scores = []
    window = max(bw // (n_estimate * 4), 5)
    for xi in range(window, bw - window):
        local_min = smooth[xi] == smooth[xi - window:xi + window + 1].min()
        if local_min and smooth[xi] < 0.85:
            valley_scores.append((smooth[xi], xi))

    valley_scores.sort()  # lowest density first
    top_valleys = sorted([x for _, x in valley_scores[:n_estimate - 1]])

    if not top_valleys:
        # Even split
        return [int(bw * i / n_estimate) for i in range(1, n_estimate)]

    return top_valleys


def split_by_rows(closed_roi, n_estimate):
    """Split a binary ROI into n_estimate row slices."""
    bh, bw = closed_roi.shape[:2]
    if bw == 0 or bh == 0:
        return []

    row_density = closed_roi.sum(axis=1).astype(float) / (bw * 255.0)
    smooth = np.convolve(row_density, np.ones(11) / 11, mode='same')

    valley_scores = []
    window = max(bh // (n_estimate * 4), 5)
    for yi in range(window, bh - window):
        local_min = smooth[yi] == smooth[yi - window:yi + window + 1].min()
        if local_min and smooth[yi] < 0.85:
            valley_scores.append((smooth[yi], yi))

    valley_scores.sort()
    top_valleys = sorted([y for _, y in valley_scores[:n_estimate - 1]])

    if not top_valleys:
        return [int(bh * i / n_estimate) for i in range(1, n_estimate)]

    return top_valleys


# ---------------------------------------------------------------------------
# Main card detection
# ---------------------------------------------------------------------------

def find_cards(img_rgb):
    """
    Returns list of 4-corner arrays [tl, tr, br, bl], sorted spatially.
    """
    h, w = img_rgb.shape[:2]
    img_area = h * w
    closed = threshold_image(img_rgb)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # ── Strategy A: individual clean card quads ────────────────────────────
    ind_cards = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 0.04 * img_area or area > 0.90 * img_area:
            continue
        peri = cv2.arcLength(cnt, True)
        for eps in [0.015, 0.025, 0.04]:
            approx = cv2.approxPolyDP(cnt, eps * peri, True)
            if len(approx) == 4:
                c = order_corners(approx)
                cw, ch = side_lengths(c)
                if is_card_aspect(cw, ch, tol=0.30):
                    ind_cards.append(c)
                break
    if ind_cards:
        return sort_spatially(ind_cards)

    # ── Strategy B: split merged blobs ─────────────────────────────────────
    # Auto-detect N from column/row profile valleys.
    # Min card width = blob_height * CARD_ASPECT * 0.5 (tolerant for partial cards)
    big_blobs = sorted(contours, key=cv2.contourArea, reverse=True)
    for blob_cnt in big_blobs[:4]:
        area = cv2.contourArea(blob_cnt)
        if area < 0.05 * img_area:
            break
        bx, by, bw_b, bh_b = cv2.boundingRect(blob_cnt)

        min_card_w = max(30, int(bh_b * CARD_ASPECT * 0.5))
        min_card_h = max(30, int(bw_b * CARD_ASPECT * 0.5))

        cards_out = []

        # Try horizontal split first (side-by-side cards)
        if bw_b > bh_b * 0.6:
            roi = closed[by:by+bh_b, bx:bx+bw_b]
            col_d = roi.sum(axis=0).astype(float) / (bh_b * 255.0)
            smooth = np.convolve(col_d, np.ones(13) / 13, mode='same')
            # Find all valleys (local minima below 0.80 that are at least min_card_w apart)
            valleys_x = []
            last_v = -min_card_w
            candidates = [(smooth[xi], xi) for xi in range(min_card_w, bw_b - min_card_w)
                          if smooth[xi] < 0.80]
            # Greedily pick valleys at least min_card_w apart, lowest density first
            for density, xi in sorted(candidates):
                if xi - last_v >= min_card_w:
                    valleys_x.append(xi)
                    last_v = xi
            valleys_x.sort()
            splits = [bx] + [bx + xi for xi in valleys_x] + [bx + bw_b]
            segs = [(splits[i], splits[i+1]) for i in range(len(splits)-1)
                    if splits[i+1] - splits[i] >= min_card_w]
            if segs:
                cards_out = [rect_corners(x0, by, x1, by+bh_b) for x0, x1 in segs]

        # Try vertical split (stacked cards)
        if not cards_out and bh_b > bw_b * 0.6:
            roi = closed[by:by+bh_b, bx:bx+bw_b]
            row_d = roi.sum(axis=1).astype(float) / (bw_b * 255.0)
            smooth = np.convolve(row_d, np.ones(13) / 13, mode='same')
            valleys_y = []
            last_v = -min_card_h
            candidates = [(smooth[yi], yi) for yi in range(min_card_h, bh_b - min_card_h)
                          if smooth[yi] < 0.80]
            for density, yi in sorted(candidates):
                if yi - last_v >= min_card_h:
                    valleys_y.append(yi)
                    last_v = yi
            valleys_y.sort()
            splits = [by] + [by + yi for yi in valleys_y] + [by + bh_b]
            segs = [(splits[i], splits[i+1]) for i in range(len(splits)-1)
                    if splits[i+1] - splits[i] >= min_card_h]
            if segs:
                cards_out = [rect_corners(bx, y0, bx+bw_b, y1) for y0, y1 in segs]

        # If still no split found, treat as single card
        if not cards_out:
            # Single card — refine to 4-corner quad via convex hull
            hull = cv2.convexHull(blob_cnt)
            peri = cv2.arcLength(hull, True)
            got = False
            for eps in [0.015, 0.03, 0.06]:
                approx = cv2.approxPolyDP(hull, eps * peri, True)
                if len(approx) == 4:
                    c = order_corners(approx)
                    cw, ch = side_lengths(c)
                    if cw > 0 and ch > 0:
                        cards_out = [c]
                        got = True
                        break
            if not got:
                cards_out = [rect_corners(bx, by, bx + bw_b, by + bh_b)]

        if cards_out:
            return sort_spatially(cards_out)

    return []


def sort_spatially(cards):
    if not cards:
        return cards
    centres = [c.mean(axis=0) for c in cards]
    xs = [float(c[0]) for c in centres]
    ys = [float(c[1]) for c in centres]
    if (max(xs) - min(xs)) >= (max(ys) - min(ys)):
        return [c for _, c in sorted(zip(xs, cards))]
    else:
        return [c for _, c in sorted(zip(ys, cards))]


# ---------------------------------------------------------------------------
# Perspective correction
# ---------------------------------------------------------------------------

def perspective_crop(img_rgb, corners):
    cw, ch = side_lengths(corners)
    dst = np.array([
        [0,      0],
        [cw - 1, 0],
        [cw - 1, ch - 1],
        [0,      ch - 1],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(img_rgb, M, (int(cw), int(ch)),
                                  flags=cv2.INTER_LANCZOS4)
    wh, ww = warped.shape[:2]
    if ww > wh:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return cv2.resize(warped, (CARD_W_PX, CARD_H_PX),
                      interpolation=cv2.INTER_LANCZOS4)


# ---------------------------------------------------------------------------
# Per-image pipeline
# ---------------------------------------------------------------------------

def process_image(heic_path, suit, card_number):
    fname = os.path.basename(heic_path)
    print(f"  [{card_number:2d}] {fname}", end="  ", flush=True)

    pil_img = Image.open(heic_path)
    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    # Landscape suits: rotate 90 CCW to make portrait
    if suit in LANDSCAPE_SUITS:
        pil_img = pil_img.rotate(90, expand=True)

    img_rgb = np.array(pil_img.convert("RGB"))

    # Downscale for detection speed; the printed inner frame is a strong,
    # consistent rectangle even when neighboring white cards touch.
    h, w = img_rgb.shape[:2]
    scale = min(1.0, 1200.0 / max(h, w))
    small = cv2.resize(img_rgb, (int(w * scale), int(h * scale))) if scale < 1.0 else img_rgb.copy()
    inner_frame = find_target_frame(small)

    # Save debug image
    debug_dir = os.path.join(OUTPUT_DIR, "_debug")
    os.makedirs(debug_dir, exist_ok=True)
    dbg = small.copy()
    if inner_frame is not None:
        cv2.polylines(dbg, [inner_frame.astype(np.int32).reshape(-1, 1, 2)], True, (0, 220, 0), 4)
    Image.fromarray(dbg).save(
        os.path.join(debug_dir, f"{suit}_{card_number:02d}_detect.jpg"),
        "JPEG", quality=72
    )

    if inner_frame is None:
        print("WARNING: MIDDLE CARD FRAME NOT DETECTED")
        return False

    corners_full = (inner_frame / scale).astype(np.float32)
    card_img = crop_card_from_frame(img_rgb, corners_full)

    out_dir = os.path.join(OUTPUT_DIR, suit)
    os.makedirs(out_dir, exist_ok=True)
    png_path = os.path.join(out_dir, f"{suit}_{card_number:02d}.png")
    Image.fromarray(card_img).save(png_path, "PNG", dpi=(DPI, DPI))
    print(f"-> {suit}_{card_number:02d}.png crop OK")
    return True


def find_target_frame(img_rgb):
    """Find the printed border nearest the image center, not arbitrary white blobs."""
    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    candidates = []
    for threshold in (70, 100, 130, 160):
        mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)[1]
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        )
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 0.06 * w * h or area > 0.70 * w * h:
                continue
            perimeter = cv2.arcLength(contour, True)
            for epsilon in (0.005, 0.01, 0.015, 0.02, 0.03):
                approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
                if len(approx) != 4:
                    continue
                corners = order_corners(approx)
                card_w, card_h = side_lengths(corners)
                aspect = card_w / card_h if card_h else 0
                if not 0.28 < aspect < 0.72:
                    continue
                cx, cy = corners.mean(axis=0)
                distance = ((cx - w / 2) / w) ** 2 + ((cy - h / 2) / h) ** 2
                candidates.append((distance, area, corners))
                break
    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    closest = candidates[0]
    nearby = [
        item for item in candidates
        if item[0] <= closest[0] + 0.005
        and np.linalg.norm(item[2].mean(axis=0) - closest[2].mean(axis=0)) < 0.035 * max(w, h)
    ]
    # A few court-card photos also produce a larger quadrilateral around the
    # rounded outside paper. The printed frame is the next, smaller rectangle;
    # reject that larger candidate when it is a clear size outlier.
    by_area = sorted(nearby, key=lambda item: item[1], reverse=True)
    area_groups = []
    for item in by_area:
        if not area_groups or area_groups[-1][0][1] > item[1] * 1.08:
            area_groups.append([item])
        else:
            area_groups[-1].append(item)
    if len(area_groups) > 1:
        largest = np.median([item[1] for item in area_groups[0]])
        next_largest = np.median([item[1] for item in area_groups[1]])
        if largest > 1.28 * next_largest:
            return max(area_groups[1], key=lambda item: item[1])[2]
    return max(area_groups[0], key=lambda item: item[1])[2]


def crop_card_from_frame(img_rgb, inner_corners):
    """Rectify the whole paper card from its printed inner border."""
    # The printed frame sits about 70% across and 87% down the card face.
    inner_w, inner_h = 1000, 2000
    # Leave a slight safety inset so the extrapolated corners do not pick up
    # the tabletop just beyond the paper edge.
    out_w = int(round(inner_w / 0.70 * 0.97))
    out_h = int(round(inner_h / 0.87 * 0.97))
    margin_x = (out_w - inner_w) / 2
    margin_y = (out_h - inner_h) / 2
    destination = np.array([
        [margin_x, margin_y],
        [margin_x + inner_w, margin_y],
        [margin_x + inner_w, margin_y + inner_h],
        [margin_x, margin_y + inner_h],
    ], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(inner_corners, destination)
    warped = cv2.warpPerspective(
        img_rgb, transform, (out_w, out_h), flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE,
    )
    card = cv2.resize(warped, (CARD_W_PX, CARD_H_PX), interpolation=cv2.INTER_LANCZOS4)
    # Photo corners can include the table around the card's rounded paper edge.
    # Keep the card silhouette and replace only the outside corner pixels with
    # the paper tone sampled from the straight edge margins.
    radius = int(round(CARD_W_PX * 0.075))
    margin = radius + 8
    edge_pixels = np.concatenate([
        card[4:16, margin:-margin].reshape(-1, 3),
        card[-16:-4, margin:-margin].reshape(-1, 3),
        card[margin:-margin, 4:16].reshape(-1, 3),
        card[margin:-margin, -16:-4].reshape(-1, 3),
    ])
    paper = np.median(edge_pixels, axis=0).astype(np.uint8)
    scale = 4
    mask = np.zeros((CARD_H_PX * scale, CARD_W_PX * scale), dtype=np.uint8)
    cv2.rectangle(mask, (radius * scale, 0), ((CARD_W_PX - radius) * scale, CARD_H_PX * scale), 255, -1)
    cv2.rectangle(mask, (0, radius * scale), (CARD_W_PX * scale, (CARD_H_PX - radius) * scale), 255, -1)
    for x in (radius * scale, (CARD_W_PX - radius) * scale):
        for y in (radius * scale, (CARD_H_PX - radius) * scale):
            cv2.circle(mask, (x, y), radius * scale, 255, -1, lineType=cv2.LINE_AA)
    mask = cv2.resize(mask, (CARD_W_PX, CARD_H_PX), interpolation=cv2.INTER_AREA)
    return np.where(mask[:, :, None] > 127, card, paper)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Trevisane Card Cropper v5")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Card size: {CARD_W_PX}x{CARD_H_PX} px ({CARD_W_MM}x{CARD_H_MM} mm @ {DPI} DPI)")
    print(f"  Landscape suits (rotate 90 CCW): {sorted(LANDSCAPE_SUITS)}")
    print()

    total = 0
    success = 0
    failed = []

    for suit in SUITS:
        print(f"=== {suit} ===")
        for card_num, filename in zip(CARD_NUMBERS, SUIT_FILES[suit]):
            heic_path = os.path.join(INPUT_DIR, suit, filename)
            if not os.path.exists(heic_path):
                print(f"  [{card_num:2d}] {filename}  -- FILE NOT FOUND")
                continue
            total += 1
            try:
                ok = process_image(heic_path, suit, card_num)
                if ok:
                    success += 1
                else:
                    failed.append(f"{suit}/{filename}")
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback; traceback.print_exc()
                failed.append(f"{suit}/{filename}")
        print()

    print("=" * 50)
    print(f"Done: {success}/{total} cards processed successfully.")
    if failed:
        print(f"Failed ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
