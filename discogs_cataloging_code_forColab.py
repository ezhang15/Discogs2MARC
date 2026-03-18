from datetime import datetime
from pymarc import Record, Field, Subfield
import string
from io import BytesIO
import discogs_client
from discogs_client.exceptions import HTTPError

def get_discogs_client(user_token: str):
    """
    Create a Discogs client using a user-supplied API token.
    """
    return discogs_client.Client(
        "lib-music-cataloging/1.0", user_token=user_token)


def strip_punctuation(input: str) -> str:
    """Remove all punctuation from a string."""
    return input.translate(str.maketrans("", "", string.punctuation))


def normalize_title(input: str) -> str:
    """Applies basic normalization to a string by stripping punctuation
    and using title case for readability.
    """
    return strip_punctuation(input.title())


def normalize(input: str) -> str:
    """Fully normalize a string for comparison with other strings.
    Strip punctuation, remove spaces, and force to upper case.
    """
    new_string = input.translate(str.maketrans("", "", string.whitespace))
    return strip_punctuation(new_string.upper())


def get_yyyymmdd() -> str:
    """Get current date as YYYYMMDD (4-digit year)."""
    return datetime.today().strftime("%Y%m%d")

def get_yymmdd() -> str:
    """Get current date as YYMMDD (2-digit year only)."""
    return datetime.today().strftime("%y%m%d")


def get_discogs_data(release_id, user_token: str):
    # Some release_id values return 404 "Release not found", even though they were just "found" by search. Example: release_id 8418329 from upc 4988006789890.
    try:
        d = get_discogs_client(user_token)
        release = d.release(release_id)
        release.refresh()
    except HTTPError as e:
        raise RuntimeError(f"Discogs API error: {e}")

    title = release.title
    artist = ", ".join([artist.name for artist in release.artists])
    publisher_number = release.labels[0].catno if release.labels else "N/A"
    full_json = release.data

    # Create a dictionary with the parsed data
    release_dict = {
        "title": title,
        "artist": artist,
        "publisher_number": publisher_number,
        "full_json": full_json,
    }
    return release_dict

def create_base_record() -> Record:
    """Create a base MARC record, to which metadata from an external
    source will be added."""
    record = Record()

    # Leader fixed field.
    # Type (Leader/06) - j (Musical sound recording)
    record.leader.type_of_record = "j"
    # BLvl (Leader/07) - m (Monographic/Item)
    record.leader.bibliographic_level = "m"
    # Ctrl (Leader/08) - # (No specified type)
    record.leader.type_of_control = " "
    # ELvl (Leader/17) - 3 (Abbreviated level)
    record.leader.encoding_level = "3"
    # Desc (Leader/18) - i (ISBD punctuation included)
    record.leader.cataloging_form = "i"

    # 008 - general information fixed field
    # DtSt (008/06) - s (Single known date/probable date) or n (Dates unknown)
    # Dat1 (008/07-10) - will be set by program if known, or uuuu if not known
    # Dat2 (008/11-14) - blanks if Dat1 is set, uuuu if Dat1 is not known
    # Ctry (008/15-17) - xx# (No place, unknown, or undetermined)
    # Comp (008/18-19) - ##
    # FMus (008/20) - n (Not applicable)
    # Part (008/21) - n (Not applicable)
    # Audn (008/22) - # (Unknown or unspecified)
    # Form (008/23) - # (None of the following)
    # AccM (008/24-29) - # (No accompanying matter)
    # LTxt (008/30-31) - # (Item is a music sound recording)
    # TrAr (008/33) - n Not arrangement or transposition or not specified
    # MRec (008/38) - # (Not modified)
    # Srce (008/39) - d (Other)
    yymmdd = get_yymmdd()
    record.add_field(
        Field(tag="008", data=f"{yymmdd}nuuuuuuuuxx ||nn           n ||| d")
    )

    # 040 ## $a CLU $b eng $c CLU
    # add_subfield method doesn't appear to work with newly created fields,
    # so we'll create the subfields first and use them to create the field
    subfields_040 = [
        Subfield("a", "CLU"),
        Subfield("b", "eng"),
        Subfield("c", "CLU"),
    ]
    field_040 = Field(tag="040", indicators=[" ", " "], subfields=subfields_040)
    record.add_field(field_040)

    # 336 ## $a performed music $b prm $2 rdacontent
    subfields_336 = [
        Subfield("a", "performed music"),
        Subfield("b", "prm"),
        Subfield("2", "rdacontent"),
    ]
    field_336 = Field(tag="336", indicators=[" ", " "], subfields=subfields_336)
    record.add_field(field_336)

    # 337 ## $a audio $b s $2 rdamedia
    subfields_337 = [
        Subfield("a", "audio"),
        Subfield("b", "s"),
        Subfield("2", "rdamedia"),
    ]
    field_337 = Field(tag="337", indicators=[" ", " "], subfields=subfields_337)
    record.add_field(field_337)

    # 338 ## $a audio disc $b sd $2 rdacarrier
    subfields_338 = [
        Subfield("a", "audio disc"),
        Subfield("b", "sd"),
        Subfield("2", "rdacarrier"),
    ]
    field_338 = Field(tag="338", indicators=[" ", " "], subfields=subfields_338)
    record.add_field(field_338)
    field_338 = Field(tag="338")

    return record


def add_discogs_data(base_record: Record, data: dict) -> Record:
    """Add metadata from a Discogs release to a MARC record. Discogs data dict
    must be in the format returned by the DiscogsClient.parse_data method."""
    # Dates (008/07-10) - release year
    year = str(data["full_json"]["year"])  # make a string for later concatenation
    # Discogs year is "0" when unknown; leave base_record's default.
    # Also be sure provided year is 4 characters.
    if year != "0" and len(year) == 4:
        f008 = base_record.get("008")
        # 008/06 = s, 008/07-10 = year, 008/11-14 = 4 blanks
        f008.data = f008.data[:6] + "s" + year + "    " + f008.data[15:]

    # Lang (008/35-37) - zxx
    f008 = base_record.get("008")
    f008.data = f008.data[:35] + "zxx" + f008.data[38:]

    # 024 8# $a IDENTIFIERS\VALUE (only for type: Barcode)
    # If no barcode element, do not include field.
    if "identifiers" in data["full_json"]:
        barcodes = set()
        for identifier in data["full_json"]["identifiers"]:
            # include only barcode values without description: Text.
            if (
                identifier.get("type") == "Barcode"
                and identifier.get("description") != "Text"
                and identifier.get("value")
            ):
                # Collect all valid values, normalize and de-dup via set.
                barcodes.add(normalize(identifier["value"]))

        # Add an 024 for each barcode found.
        for value in barcodes:
            subfields_024 = [Subfield("a", value)]
            field_024 = Field(tag="024", indicators=["8", " "], subfields=subfields_024)
            base_record.add_ordered_field(field_024)

    # 028 12 $a IDENTIFIERS\VALUE (only for type: Matrix / Runout)
    # If no matrix element, do not include field.
    if "identifiers" in data["full_json"]:
        if "labels" in data["full_json"]:
            label = data["full_json"]["labels"][0]
            if "name" in label:
                publisher = label["name"]
            else:
                publisher = "[publisher not identified]"
        else:
            publisher = "[publisher not identified]"

        matrices = set()
        for identifier in data["full_json"]["identifiers"]:
            if (
                identifier.get("type") == "Matrix / Runout"
                and identifier.get("value")
            ):
                # Collect all valid values, normalize and de-dup via set.
                matrices.add(identifier["value"])

        # Add an 028 for each barcode found.
        for value in matrices:
            subfields_028 = [Subfield("a", value), Subfield("b", publisher), Subfield("q", "(matrix)")]
            field_028 = Field(tag="028", indicators=["1", "2"], subfields=subfields_028)
            base_record.add_ordered_field(field_028)

    # 028 02 $a LABELS\CATNO $b LABELS\NAME
    # If no labels\catno element, do not include field.
    if "labels" in data["full_json"]:
        # Collect values (catno and name) via dict to de-dup.
        labels = {}
        for label in data["full_json"]["labels"]:
            # If there are multiple labels\catno elements, create multiple 028 fields.
            # If no labels\name element, do not include $b.
            # Same catno ($a) + different name ($b) is OK, but remove full duplicates.
            catno = label.get("catno")
            name = label.get("name")
            normalized_key = normalize(catno + name)
            # Preserve the first occurrence of a key, so add only if not already present.
            if normalized_key not in labels:
                labels[normalized_key] = (catno, name)

        # Ignore keys, use now-deduped catno and name to create 028 fields.
        for normalized_key, (catno, name) in labels.items():
            subfields_028 = [Subfield("a", catno)]
            if name:
                subfields_028.append(Subfield("b", name))
            field_028 = Field(tag="028", indicators=["0", "2"], subfields=subfields_028)
            base_record.add_ordered_field(field_028)

    # 245 00 $a TITLE / $c ARTISTS\NAME
    title_245 = data["title"]
    # first artist only
    if "artist" in data:
        artist_245 = data["artist"]
        # format: $a Title <space> <slash> $c Artists\name <period>
        subfields_245 = [
            Subfield("a", title_245.capitalize() + " /"),
            Subfield("c", artist_245 + "."),
        ]
    else:
        # format: $a Title <period>
        subfields_245 = [Subfield("a", title_245.capitalize() + ".")]
    # if the first word of the title=”the” then 2nd indicator=4.
    # if the first word of the title=”a” then 2nd indicator=2.
    if title_245.lower().startswith("the "):
        field_245 = Field(tag="245", indicators=["0", "4"], subfields=subfields_245)
    elif title_245.lower().startswith("a "):
        field_245 = Field(tag="245", indicators=["0", "2"], subfields=subfields_245)
    elif title_245.lower().startswith("an "):
        field_245 = Field(tag="245", indicators=["0", "3"], subfields=subfields_245)
    else:
        field_245 = Field(tag="245", indicators=["0", "0"], subfields=subfields_245)
    base_record.add_ordered_field(field_245)

    # 264 #1 $a [Place of publication not identified] : $b LABELS\NAME, $c [RELEASED]
    # For DATE - 1st 4 digits only
    # If no label-info\label\name element, fill in $b with “[publisher not identified]”
    # If there are multiple label-info\label\name elements, take only the first instance.
    # If no date element, fill in $c with “[date of publication not identified]”
    date_264 = str(data["full_json"]["year"])  # make a string for later concatenation
    if date_264 == "0":
        date_264 = "date of publication not identified"

    if "labels" in data["full_json"]:
        label = data["full_json"]["labels"][0]
        if "name" in label:
            publisher = label["name"]
        else:
            publisher = "[publisher not identified]"
    else:
        publisher = "[publisher not identified]"

    # format: [Place of publication not identified] <space> <colon>$b  LABELS\NAME <comma>
    # $c <open square bracket>RELEASED<closed square bracket>
    subfields_264 = [
        Subfield("a", "[Place of publication not identified] :"),
        Subfield("b", publisher + ","),
        Subfield("c", "[" + date_264 + "]"),
    ]
    field_264 = Field(tag="264", indicators=[" ", "1"], subfields=subfields_264)
    base_record.add_ordered_field(field_264)

    # 500 ## $a Record generated from Discogs database.
    # constant value
    subfields_500 = [Subfield("a", "Record generated from Discogs database.")]
    field_500 = Field(tag="500", indicators=[" ", " "], subfields=subfields_500)
    base_record.add_ordered_field(field_500)

    # 505 0# $a TRACKLIST\TITLE -- TRACKLIST\TITLE -- TRACKLIST\TITLE […].
    # If no tracklist element, do not include field.
    if "tracklist" in data["full_json"]:
        # Grab all track titles.
        track_titles = [track["title"].capitalize() for track in data["full_json"]["tracklist"]]
        # Format into one string, separated by " -- ", ending with period.
        contents = " -- ".join(track_titles) + "."
        subfields_505 = [Subfield("a", contents)]
        field_505 = Field(tag="505", indicators=["0", " "], subfields=subfields_505)
        base_record.add_ordered_field(field_505)

    # 653 #6 $a GENRES
    # include all genres in $a subfields
    if "genres" in data["full_json"]:
        subfields_653 = []
        for genre in data["full_json"]["genres"]:
            subfields_653.append(Subfield("a", genre))
            field_653 = Field(tag="653", indicators=[" ", "6"], subfields=subfields_653)
        base_record.add_ordered_field(field_653)

    # 720 ## $a ARTISTS_SORT.
    # single string fields with possible multiple artists
    artist_720 = data["full_json"]["artists_sort"]
    # format: $a ARTISTS_SORT.
    subfields_720 = [Subfield("a", artist_720 + ".")]
    field_720 = Field(tag="720", indicators=[" ", " "], subfields=subfields_720)
    base_record.add_ordered_field(field_720)

    # Conditional fields based on format of item. Either vinyl or CD.
    if "formats" in data["full_json"]:

        format_type = data["full_json"]["formats"][0].get("name")
        # Fields specific to vinyl format
        if format_type == "Vinyl":

            # 007 - physical description fixed field
            # 007 ## $a s $b d $d \ $e s $f m $g e $h n $i n $j m $k p $l l $m u $n e
            # translated to fixed field:
            base_record.add_ordered_field(Field(tag="007", data="sd\bumennmplnu"))

            qty = data["full_json"]["formats"][0].get("qty", "1")
            if int(qty) > 1:
                qty_text = qty + " audio discs ;"
            else:
                qty_text = qty + " audio disc ;"

            # format: $a FORMATS\QTY audio disc <space> <colon> $c 12 in.
            subfields_300 = [
                Subfield("a", qty_text),
                Subfield("c", "12 in."),
            ]
            field_300 = Field(tag="300", indicators=[" ", " "], subfields=subfields_300)
            base_record.add_ordered_field(field_300)

            # 340 ## physical medium
            subfields_340 = [Subfield("a", "vinyl"), Subfield("2", "rdamat")]
            field_340 = Field(tag="340", indicators=[" ", " "], subfields=subfields_340)
            base_record.add_ordered_field(field_340)

            # 344 ## sound characteristics - analog
            subfields_344_1 = [Subfield("a", "analog"), Subfield("2", "rdatr")]
            field_344_1 = Field(tag="344", indicators=[" ", " "], subfields=subfields_344_1)
            base_record.add_ordered_field(field_344_1)

            # 344 ## sound characteristics - rpm
            subfields_344_2 = [Subfield("c", "33 1/3 rpm")]
            field_344_2 = Field(tag="344", indicators=[" ", " "], subfields=subfields_344_2)
            base_record.add_ordered_field(field_344_2)

            # 344 ## sound characteristics - microgrove
            subfields_344_3 = [Subfield("d", "microgrove"), Subfield("2", "rdagw")]
            field_344_3 = Field(tag="344", indicators=[" ", " "], subfields=subfields_344_3)
            base_record.add_ordered_field(field_344_3)

        # Fields specific to CD format
        elif format_type == "CD":

            # 007 - physical description fixed field
            # 007 ## $a s $b d $d f $e u $f n $g g $h n $i n $m e $n u
            # translated to fixed field:
            base_record.add_ordered_field(Field(tag="007", data="sd fungnn|||eu"))

            qty = data["full_json"]["formats"][0].get("qty", "1")
            if int(qty) > 1:
                qty_text = qty + " audio discs :"
            else:
                qty_text = qty + " audio disc :"

            # format: $a FORMATS\QTY audio disc <space> <colon> $b digital <space> <semicolon> $c 4 3/4 in.
            subfields_300 = [
                Subfield("a", qty_text),
                Subfield("b", "digital ;"),
                Subfield("c", "4 3/4 in."),
            ]
            field_300 = Field(tag="300", indicators=[" ", " "], subfields=subfields_300)
            base_record.add_ordered_field(field_300)

            # 340 ## $b 4 3/4 in.
            subfields_340 = [Subfield("b", "4 3/4 in.")]
            field_340 = Field(tag="340", indicators=[" ", " "], subfields=subfields_340)
            base_record.add_ordered_field(field_340)

            # 344 ## $a digital $2 rdatr
            subfields_344_1 = [Subfield("a", "digital"), Subfield("2", "rdatr")]
            field_344_1 = Field(tag="344", indicators=[" ", " "], subfields=subfields_344_1)
            base_record.add_ordered_field(field_344_1)

            # 344 ## $b optical $2 rdarm
            subfields_344_2 = [Subfield("b", "optical"), Subfield("2", "rdarm")]
            field_344_2 = Field(tag="344", indicators=[" ", " "], subfields=subfields_344_2)
            base_record.add_ordered_field(field_344_2)

            # 347 ## $a audio file $2 rdaft
            subfields_347_1 = [Subfield("a", "audio file"), Subfield("2", "rdaft")]
            field_347_1 = Field(tag="347", indicators=[" ", " "], subfields=subfields_347_1)
            base_record.add_ordered_field(field_347_1)

            # 347 ## $b CD audio
            subfields_347_2 = [Subfield("b", "CD audio")]
            field_347_2 = Field(tag="347", indicators=[" ", " "], subfields=subfields_347_2)
            base_record.add_ordered_field(field_347_2)

    return base_record


def create_discogs_record(data: dict) -> Record:
    """Convenience method to create MARC record from base record
    and Discogs data."""
    base_record = create_base_record()
    return add_discogs_data(base_record, data)

def create_marc_record(record: Record) -> BytesIO:
    output_buffer = BytesIO()
    output_buffer.write(record.as_marc21())
    output_buffer.seek(0)
    return output_buffer
