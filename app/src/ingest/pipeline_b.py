import argparse
from src.ingest.pipeline_common import run_pipeline


def run_pipeline_b(input_dir: str) -> dict:
    return run_pipeline(input_dir, 'internal_regulations')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    args = parser.parse_args()
    print(run_pipeline_b(args.input))
