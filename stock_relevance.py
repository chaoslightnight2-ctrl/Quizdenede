"""Rank actual stock asset descriptions before resolution or random diversity."""
import re

def relevance(query, asset):
    ignored={'video','videos','footage','vertical','portrait','background','scene','scenes'}
    def tokens(value):
        return {w[:-1] if len(w)>4 and w.endswith('s') else w
                for w in re.findall(r'[a-z]+',str(value).lower()) if w not in ignored}
    wanted=tokens(query)
    description=' '.join(str(asset.get(k,'')) for k in ('url','title','description','alt','tags'))
    return len(wanted & tokens(description))/max(1,len(wanted))
