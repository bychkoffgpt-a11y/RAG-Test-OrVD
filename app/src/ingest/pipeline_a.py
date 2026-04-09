import argparse
from src.core.settings import settings
from src.ingest.pipeline_common import run_pipeline


def run_pipeline_a(input_dir: str) -> dict:
    return run_pipeline(
        input_dir,
        'csv_ans_docs',
        chunk_size=settings.chunk_size_csv_ans_docs,
        overlap=settings.chunk_overlap_csv_ans_docs,
        chunk_strategy=settings.chunk_strategy_csv_ans_docs,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    args = parser.parse_args()
    print(run_pipeline_a(args.input))
