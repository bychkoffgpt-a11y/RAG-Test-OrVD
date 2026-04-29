from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from score_vlm_results_v2 import load_aliases, score_fact_hard, score_fact_partial, score_fact_semantic_hard


def test_img02_invoice_date_and_currency_normalization():
    aliases = load_aliases()
    answer = "Invoice A-1024 от 15 мая 2026, итог: 849,90 USD."
    hard, _ = score_fact_hard(answer, "Есть дата 2026-05-15", aliases)
    part, _ = score_fact_partial(answer, "Есть сумма 849.90", aliases)
    assert hard == 0.0
    assert part >= 0.9


def test_img08_pie_sector_equivalence_partial():
    aliases = load_aliases()
    answer = "На изображении секторная диаграмма: Chrome самый большой сегмент, Safari самый маленький."
    hard, _ = score_fact_hard(answer, "Это круговая диаграмма", aliases)
    part, _ = score_fact_partial(answer, "Это круговая диаграмма", aliases)
    assert hard == 0.0
    assert part >= 0.9


def test_img05_chart_semantic_q_and_trend_and_extremum():
    aliases = load_aliases()
    answer = "На графике есть Q1, Q2, Q3, Q4; наблюдается рост к Q4, самый высокий столбец — Q4, самый низкий — Q1."
    sem_q, _ = score_fact_semantic_hard(answer, "На графике присутствуют Q1 Q2 Q3 Q4", aliases)
    sem_trend, _ = score_fact_semantic_hard(answer, "На графике есть рост по кварталам", aliases)
    sem_extreme, _ = score_fact_semantic_hard(answer, "Самый высокий показатель у Q4, самый низкий у Q1", aliases)
    assert sem_q == 1.0
    assert sem_trend == 1.0
    assert sem_extreme == 1.0


def test_img12_schedule_note_text_equivalence():
    aliases = load_aliases()
    answer = "Текстовая заметка: Meeting 10:30, Room C-7, Owner Nina."
    hard, _ = score_fact_hard(answer, "Это текстовая заметка/расписание", aliases)
    part, _ = score_fact_partial(answer, "Это текстовая заметка/расписание", aliases)
    assert hard == 0.0
    assert part >= 0.8
