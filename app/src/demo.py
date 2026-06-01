from __future__ import annotations

import re
import sys
from collections.abc import Generator,Iterator
from contextlib import contextmanager
from dataclasses import dataclass,field
from typing import ClassVar,Generic,Protocol,TypeAlias,TypedDict,TypeVar,overload,runtime_checkable

# ── Types ─────────────────────────────────────────────────────────────────────

T=TypeVar('T')
Score:TypeAlias=float

@runtime_checkable
class Applicable(Protocol):
    def apply(self,text:str)->str: ...

class RuleDict(TypedDict):
    pattern:str
    replacement:str
    priority:int

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass(slots=True)
class Rule:
    pattern:str
    replacement:str
    priority:int=0
    flags:re.RegexFlag=re.IGNORECASE
    _compiled:re.Pattern[str]=field(init=False,repr=False)

    def __post_init__(self)->None:
        self._compiled=re.compile(self.pattern,self.flags)

    def apply(self,text:str)->str:
        return self._compiled.sub(self.replacement,text)

    @classmethod
    def from_dict(cls,d:RuleDict)->Rule:
        return cls(pattern=d['pattern'],replacement=d['replacement'],priority=d['priority'])

    @staticmethod
    def escape(pattern:str)->str:
        return re.escape(pattern)

# ── Generic class ─────────────────────────────────────────────────────────────

@dataclass
class Scored(Generic[T]):
    value:T
    score:Score

    def __lt__(self,other:Scored[T])->bool:
        return self.score<other.score

# ── Pipeline ──────────────────────────────────────────────────────────────────

@dataclass
class Pipeline:
    name:str
    rules:list[Rule]=field(default_factory=list)
    _stats:dict[str,int]=field(default_factory=dict,repr=False)
    _call_count:ClassVar[int]=0

    def add(self,*rules:Rule)->Pipeline:
        self.rules.extend(sorted(rules,key=lambda r:r.priority,reverse=True))
        return self

    def run(self,text:str)->str:
        Pipeline._call_count+=1
        for rule in self.rules:
            before=text
            text=rule.apply(text)
            if text!=before:
                self._stats[rule.pattern]=self._stats.get(rule.pattern,0)+1
        return text

    def run_many(self,texts:list[str])->Generator[str,None,None]:
        for text in texts:
            yield self.run(text)

    @property
    def stats(self)->dict[str,int]:
        return dict(self._stats)

    @classmethod
    def total_calls(cls)->int:
        return cls._call_count

# ── Overload ──────────────────────────────────────────────────────────────────

@overload
def make_rule(spec:str)->Rule: ...
@overload
def make_rule(spec:RuleDict)->Rule: ...

def make_rule(spec:str|RuleDict)->Rule:
    match spec:
        case str(s):
            return Rule(pattern=s,replacement='')
        case {'pattern':p,'replacement':r,'priority':pri}:
            return Rule(pattern=p,replacement=r,priority=pri)
        case {'pattern':p,'replacement':r}:
            return Rule(pattern=p,replacement=r)
        case _:
            raise ValueError(f"invalid spec: {spec!r}")

# ── Context manager ───────────────────────────────────────────────────────────

@contextmanager
def pipeline_session(name:str)->Iterator[Pipeline]:
    p=Pipeline(name=name)
    try:
        yield p
    finally:
        print(f"[{name}] done, stats={p.stats}",file=sys.stderr)

# ── Walrus & union types ──────────────────────────────────────────────────────

def find_first(rules:list[Rule],text:str)->Rule|None:
    return next((r for r in rules if (m:=r._compiled.search(text)) and m),None)

def score_texts(pipeline:Pipeline,texts:list[str],threshold:Score=0.0)->list[Scored[str]]:
    results=[]
    for raw in texts:
        out=pipeline.run(raw)
        score=len(out)/max(len(raw),1)
        if score>threshold:
            results.append(Scored(value=out,score=score))
    return sorted(results,reverse=True)

def build_default()->Pipeline:
    return Pipeline(name='default').add(
        Rule(r'\s+',' ',priority=10),
        Rule(r'^\s+|\s+$','',priority=9),
        Rule(r'(\w)\s*=\s*(\w)',r'\1 = \2',priority=5),
        Rule(r',(\S)',r', \1',priority=5),
    )

def process_batch(pipeline:Pipeline,texts:list[str],verbose:bool=False)->list[str]:
    return [pipeline.run(t) for t in texts if (verbose and print(f"processing: {t!r}",file=sys.stderr)) or True]

# ── main ──────────────────────────────────────────────────────────────────────

def main(argv:list[str])->int:
    text=' '.join(argv) if argv else 'x=1,y=2,  z =  3'
    with pipeline_session('main') as pipeline:
        pipeline.add(*build_default().rules)
        result=pipeline.run(text)
        print(result)
        scored=score_texts(pipeline,[text,'  hello  world  ','a=1,b=2'])
        for s in scored:
            print(f"  score={s.score:.3f} value={s.value!r}")
        print(f"total pipeline calls: {Pipeline.total_calls()}",file=sys.stderr)
    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv[1:]))
