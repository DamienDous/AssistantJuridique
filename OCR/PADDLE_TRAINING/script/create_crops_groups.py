import csv
A,B,C = open("train_A.txt","w",encoding="utf-8"), open("train_B.txt","w",encoding="utf-8"), open("train_C.txt","w",encoding="utf-8")
with open("quality_metrics.csv",encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter=";")
    for row in r:
        p = row["path"]; lab = row["label"]
        w = float(row["w"]); h = float(row["h"]); ratio = float(row["ratio"])
        lap = float(row["lap_var"]); std = float(row["std"]); mean=float(row["mean"])
        black = float(row["black"]); edge = float(row["edge_ink"])
        oov = int(row["oov"]); length = int(row["len"])
        too_small = int(row["too_small_h"]); crazy = int(row["crazy_ratio"])

        condA = (h>=22 and ratio<=10 and edge<=0.02 and lap>=60 and std>=25 and 0.15<=black<=0.85 and oov==0 and 3<=length<=80 and not too_small and not crazy)
        condC = (too_small or crazy or edge>0.08 or oov>0 or h<16 or ratio>20 or lap<20 or std<10 or black<0.05 or black>0.95)

        if condA:
            A.write(f"{p}\t{lab}\n")
        elif condC:
            C.write(f"{p}\t{lab}\n")
        else:
            B.write(f"{p}\t{lab}\n")
A.close(); B.close(); C.close()
print("[OK] groupés → train_A.txt / train_B.txt / train_C.txt")