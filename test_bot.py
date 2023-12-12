import argparse

import process_request

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t",
        "--task",
        action="store",
        help="id of the task to try bot on",
        type=int,
        required=True
    )
    args = parser.parse_args()

    process_request.process_thread(args.task)
