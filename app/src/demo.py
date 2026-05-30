from dataclasses import dataclass,field
from typing import Optional
import re,sys

@dataclass
class Rule:
    pattern:str
    replacement:str
    priority:int=0
    flags:re.RegexFlag=re.IGNORECASE

    def apply(self,text:str)->str:
        return re.sub(self.pattern,self.replacement,text,flags=self.flags)

@dataclass
class Pipeline:
    name:str
    rules:list[Rule]=field(default_factory=list)
    _stats:dict=field(default_factory=dict,repr=False)

    def add(self,*rules:Rule)->'Pipeline':
        self.rules.extend(sorted(rules,key=lambda r:r.priority,reverse=True))
        return self

    def run(self,text:str)->str:
        for rule in self.rules:
            before=text
            text=rule.apply(text)
            if text!=before:
                self._stats[rule.pattern]=self._stats.get(rule.pattern,0)+1
        return text

    @property
    def stats(self)->dict:
        return dict(self._stats)

def build_default()->Pipeline:
    return Pipeline(name='default').add(
        Rule(r'\s+',' ',priority=10),
        Rule(r'^\s+|\s+$','',priority=9),
        Rule(r'(\w)\s*=\s*(\w)',r'\1 = \2',priority=5),
        Rule(r',(\S)',r', \1',priority=5),
    )

def main(argv:list[str])->int:
    text=' '.join(argv) if argv else 'x=1,y=2,  z =  3'
    pipeline=build_default()
    result=pipeline.run(text)
    print(result)
    print(pipeline.stats,file=sys.stderr)
    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv[1:]))
