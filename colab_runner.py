
# colab_runner.py

from getpass import getpass
from discogs_cataloging_code_forColab import (
    get_discogs_data,
    create_discogs_record,
    create_marc_record,
)
from IPython.display import display, Markdown
from google.colab import files


def main():
    display(Markdown("## Discogs → MARC Cataloging Tool"))

    # --- Prompt for credentials / input ---
    user_token = getpass("Enter your Discogs user token: ").strip()
    if not user_token:
        raise ValueError("No Discogs token provided.")

    release_id = input("Enter Discogs release ID (e.g. 34044358): ").strip()
    if not release_id:
        raise ValueError("No release ID provided.")

    # --- Fetch Discogs data ---
    display(Markdown("### Fetching data from Discogs…"))
    data = get_discogs_data(release_id, user_token)

    # --- Create MARC record ---
    record = create_discogs_record(data)

    # --- Display MARC output (human‑readable) ---
    display(Markdown("### MARC record output"))
    display(Markdown("```\n" + str(record) + "\n```"))

    # --- Write MARC file ---
    marc_buffer = create_marc_record(record)
    output_file = "discogs_result.mrc"

    with open(output_file, "wb") as f:
        f.write(marc_buffer.getvalue())

    # --- Download link ---
    display(Markdown("### Download MARC file"))
    files.download(output_file)


if __name__ == "__main__":
    main()
``
