import os, cv2, numpy as np, unicodedata, regex as re, csv
from multiprocessing import Pool

LIST_IN = "train_short/output/train.txt"    # lignes: path\tlabel
CSV_OUT = "eval/quality_metrics.csv"
DICT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZÀÂÇÉÈÊËÎÏÔÙÛÜŸŒÆàâçéèêëîïôùûüÿœæ0123456789 .,;:!?\"'()-")

def normalize(txt):
    if txt is None: return ""
    t = unicodedata.normalize("NFKC", txt)
    t = (t.replace("’","'")
           .replace("–","-").replace("—","-")
           .replace("“",'"').replace("”",'"')
           .replace("œ","oe").replace("Œ","Oe")
           .replace("æ","ae").replace("Æ","Ae"))
    t = re.sub(r"\s+"," ",t.strip())
    return t

def metrics(line):
    try:
        p, lab = line.rstrip("\n").split("\t",1)
    except ValueError:
        return None
    lab_n = normalize(lab)
    oov = sum(1 for c in lab_n if not (c in DICT or c.isspace()))
    len_lab = len(lab_n)

    path = "train_short/" + p
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return [p, len_lab, oov, -1,-1,-1,-1,-1,-1,-1,-1, 1, 1, "missing"]
    h, w = im.shape[:2]
    ratio = w / max(1,h)

    # Netteté / contraste / luminosité
    lap = cv2.Laplacian(im, cv2.CV_64F).var()
    std = float(np.std(im))
    mean = float(np.mean(im))

    # Binarisation Otsu → ratio noir/blanc
    _, bw = cv2.threshold(im,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    black_ratio = float((bw==0).mean())
    white_ratio = float((bw==255).mean())

    # Encre touchant les bords (caractères coupés)
    th = cv2.threshold(im,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    edge_top = (th[0,:]==0).mean()
    edge_bot = (th[-1,:]==0).mean()
    edge_lft = (th[:,0]==0).mean()
    edge_rgt = (th[:,-1]==0).mean()
    edge_ink = float(np.mean([edge_top,edge_bot,edge_lft,edge_rgt]))

    # Artefacts JPEG approx: énergie HF
    hf = cv2.Laplacian(cv2.GaussianBlur(im,(3,3),0), cv2.CV_64F)
    jpeg_hf = float(np.mean(np.abs(hf)))

    # Flags rapides
    too_small_h = 1 if h < 18 else 0
    crazy_ratio = 1 if ratio > 15 else 0

    return [p, len_lab, oov, w, h, ratio, lap, std, mean, black_ratio, white_ratio, edge_ink, jpeg_hf, too_small_h, crazy_ratio, lab_n]

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()  # requis sous Windows

    with open(LIST_IN, encoding="utf-8") as f:
        lines = f.readlines()

    with Pool() as pool, open(CSV_OUT, "w", newline="", encoding="utf-8") as g:
        wcsv = csv.writer(g, delimiter=";")
        wcsv.writerow(["path","len","oov","w","h","ratio","lap_var","std","mean",
                       "black","white","edge_ink","jpeg_hf","too_small_h",
                       "crazy_ratio","label"])
        for res in pool.imap_unordered(metrics, lines, chunksize=1000):
            if res is None:
                continue
            wcsv.writerow(res)

    print("[OK] écrit:", CSV_OUT)