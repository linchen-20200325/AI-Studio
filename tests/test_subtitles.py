from see.core.subtitles import build_cues, chunk_for_display, split_sentences, to_srt


def test_split_keeps_terminal_punctuation():
    assert split_sentences("你好。再見！好嗎？") == ["你好。", "再見！", "好嗎？"]


def test_chunk_respects_max_chars():
    text = "從前有一座山，山上有一間小廟，廟裡住著一位老和尚和一個小和尚。"
    for c in chunk_for_display(text, 18):
        assert len(c) <= 18


def test_chunk_hard_splits_long_run():
    assert chunk_for_display("一" * 40, 18) == ["一" * 18, "一" * 18, "一" * 4]


def test_cues_cover_duration_proportionally():
    cues = build_cues("第一句。第二句比較長一點點。", 10.0, max_chars=8)
    assert cues[0].start == 0.0
    assert abs(cues[-1].end - 10.0) < 1e-6
    assert all(c.end > c.start for c in cues)
    assert cues[1].end - cues[1].start > cues[0].end - cues[0].start


def test_empty_text_gives_no_cues_and_empty_srt():
    assert build_cues("", 5.0) == []
    assert to_srt([]) == ""


def test_srt_format():
    srt = to_srt(build_cues("你好。", 1.5))
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\n你好。\n")
