"""python cli.py request.json > result.json; python cli.py --check result.json"""
import argparse,json,hashlib
from dataclasses import asdict
from model import DB,Preferences,load_catalog
from optimizer import solve
from checker import check

def preferences(raw):
    raw=dict(raw)
    raw['weekdays']={int(k):v for k,v in raw.get('weekdays',{}).items()}
    return Preferences(**raw)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('file');parser.add_argument('--check',action='store_true');args=parser.parse_args()
    with open(args.file,encoding='utf-8') as f: data=json.load(f)
    cat=load_catalog();p=preferences(data.get('preferences',{}));codes=data['courses']
    if args.check:
        sols=data.get('solutions',[data['solution']] if 'solution' in data else [])
        if not sols:raise SystemExit('文件中没有可验证方案')
        output=[check(cat,codes,s['selections'],p) for s in sols]
    else:
        result=solve(cat,codes,p,timeout=data.get('timeout',15))
        output=asdict(result)
        output.update(courses=codes,preferences=asdict(p),database_sha256=hashlib.sha256(DB.read_bytes()).hexdigest())
        for s in output['solutions']:s['validation']=check(cat,codes,s['selections'],p)
    print(json.dumps(output,ensure_ascii=False,indent=2))
