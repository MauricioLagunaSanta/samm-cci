"""Mide el acierto del validador de relevancia contra el gold set etiquetado a mano.

    cd backend
    python ../scripts/evaluate_relevance.py                       # usa tests/gold_set/relevancia.csv
    python ../scripts/evaluate_relevance.py ruta/otro_gold.csv

Cada fila etiquetada (relevante = 1 o 0) se cruza con la BD por URL o, si no hay URL, por el inicio
del titular. Las filas sin etiqueta se ignoran. "Revisar" NO se cuenta como acierto ni como error
automático: se reporta aparte porque es la carga que queda para una persona.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from sqlalchemy import select  # noqa: E402

from app.classification.relevance import normalize  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.models import EstadoRelevancia as E  # noqa: E402
from app.models import Mencion  # noqa: E402

DEFAULT_CSV = Path("tests/gold_set/relevancia.csv")


def buscar(session, fila, todas):
    if fila["url"].strip():
        return session.scalars(select(Mencion).where(Mencion.url == fila["url"].strip())).first()
    inicio = normalize(fila["titular_inicio"].rstrip(".… "))
    return next((m for m in todas if normalize(m.titular).startswith(inicio)), None)


def main(ruta: Path) -> int:
    init_db()
    with open(ruta, encoding="utf-8", newline="") as fh:
        filas = [r for r in csv.DictReader(fh) if r["relevante"].strip() in ("0", "1")]
    if not filas:
        print("El gold set no tiene filas etiquetadas (columna 'relevante' = 0 o 1).")
        return 1

    tp = fp = tn = fn = revisar = 0
    errores, sin_bd = [], []
    with SessionLocal() as s:
        todas = s.scalars(select(Mencion)).all()
        for f in filas:
            m = buscar(s, f, todas)
            real = f["relevante"].strip() == "1"
            if m is None:
                sin_bd.append(f["titular_inicio"])
            elif m.estado_relevancia == E.REVISAR:
                revisar += 1
            elif m.estado_relevancia == E.PENDIENTE:
                sin_bd.append(f"{f['titular_inicio']} (sin validar)")
            else:
                pred = m.estado_relevancia == E.VALIDA
                tp += pred and real
                fp += pred and not real
                tn += (not pred) and (not real)
                fn += (not pred) and real
                if pred != real:
                    errores.append(f"{'FALSO POSITIVO' if pred else 'FALSO NEGATIVO'}: {m.titular}\n   {m.motivo_relevancia}")

    decididas = tp + fp + tn + fn
    print(f"Etiquetadas: {len(filas)} | decididas por el sistema: {decididas} | a Revisar: {revisar} | no evaluables: {len(sin_bd)}")
    if decididas:
        print(f"Exactitud (sobre decididas): {(tp + tn) / decididas:.1%}")
        print(f"Precisión: {tp / (tp + fp):.1%}" if tp + fp else "Precisión: n/a")
        print(f"Recall:    {tp / (tp + fn):.1%}" if tp + fn else "Recall: n/a")
    print(f"Exactitud estricta (Revisar cuenta como fallo): {(tp + tn) / (decididas + revisar):.1%}" if decididas + revisar else "")
    for e in errores:
        print(e)
    for t in sin_bd:
        print(f"No evaluable: {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV))
