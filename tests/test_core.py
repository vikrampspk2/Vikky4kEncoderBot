from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workers.downloader import extract_url

def test_extract_url():
    assert extract_url('hello https://example.com/video.mp4?q=1, okay') == 'https://example.com/video.mp4?q=1'
    assert extract_url('no url here') is None
