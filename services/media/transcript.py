"""
Transcript retrieval (section 11 pipeline step).

SavedFlow does not build an unauthorized Instagram downloader (section 4),
so there is no automatic transcript extraction from the Instagram video
itself in V1. This module exists as the single, clearly-named place a
transcript would be looked up, so that:

  1. A future, legitimate transcript source (e.g. a transcript the user
     pastes in manually via user_notes, or a licensed captioning API) can
     be plugged in here without changing analyzer.py.
  2. Today, it simply looks for a transcript the user has explicitly
     attached to the item (item["transcript"]), and returns None otherwise
     - which correctly routes analysis to METADATA_ONLY.
"""


def get_transcript_if_available(item):
    transcript = item.get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip()
    return None
