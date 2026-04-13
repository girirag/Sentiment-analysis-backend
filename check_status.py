import json, pathlib

vid = '39d9f073-7a79-4cea-a9bd-bd59a49509b9'
analysis = pathlib.Path(f'uploads/{vid}_analysis.json')
videos_file = pathlib.Path('uploads/videos.json')

with open(videos_file) as f:
    videos = json.load(f)
for v in videos:
    if v['video_id'] == vid:
        print(f"Title  : {v['title']}")
        print(f"Status : {v['status']}")
        print(f"Created: {v['created_at']}")
        break

if analysis.exists():
    with open(analysis) as f:
        data = json.load(f)
    segs = data.get('timeline', data.get('transcription', []))
    print(f"Analysis: EXISTS — {len(segs)} segments")
    print(f"Sentiment: {data.get('overall_sentiment', 'N/A')}")
else:
    print("Analysis: NOT YET AVAILABLE (still processing)")
