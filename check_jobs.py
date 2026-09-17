
import os, glob, json
jobs = sorted(glob.glob('backend/data/jobs/*.json'), key=os.path.getmtime, reverse=True)
for j in jobs[:5]:
    try:
        with open(j) as f:
            data = json.load(f)
            s = data.get('status')
            m = data.get('model')
            e = data.get('error_reason')
            print(f'{j} - Status: {s} - Model: {m} - Error: {e}')
    except Exception as e:
        print(e)

