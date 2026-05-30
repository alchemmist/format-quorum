import os,sys
from typing import List,Dict,Optional
from dataclasses import dataclass

@dataclass
class Config:
    host:str
    port:int=8080
    debug:bool=False
    tags:List[str]=None

    def __post_init__(self):
        if self.tags is None:
            self.tags=[]

def parse_args(argv:List[str])->Dict[str,str]:
    result={}
    i=0
    while i<len(argv):
        if argv[i].startswith('--'):
            key=argv[i][2:]
            if i+1<len(argv) and not argv[i+1].startswith('--'):
                result[key]=argv[i+1]
                i+=2
            else:
                result[key]=True
                i+=1
        else:
            i+=1
    return result

class Server:
    def __init__(self,config:Config):
        self.config=config
        self._running=False
        self._handlers={}

    def route(self,path:str):
        def decorator(fn):
            self._handlers[path]=fn
            return fn
        return decorator

    def start(self):
        self._running=True
        if self.config.debug:
            print(f'Starting server on {self.config.host}:{self.config.port}')

    def stop(self):
        self._running=False

    def dispatch(self,path:str,request:dict)->Optional[dict]:
        handler=self._handlers.get(path)
        if handler is None:
            return {'status':404,'body':'Not found'}
        try:
            return handler(request)
        except Exception as e:
            return {'status':500,'body':str(e)}

def main():
    args=parse_args(sys.argv[1:])
    cfg=Config(
        host=args.get('host','0.0.0.0'),
        port=int(args.get('port',8080)),
        debug='debug' in args,
        tags=args.get('tags','').split(',') if 'tags' in args else [],
    )
    srv=Server(cfg)

    @srv.route('/health')
    def health(req):
        return {'status':200,'body':'ok'}

    @srv.route('/info')
    def info(req):
        return {'status':200,'body':{'host':cfg.host,'port':cfg.port,'tags':cfg.tags}}

    srv.start()
    print(f'Listening on {cfg.host}:{cfg.port}')

if __name__=='__main__':
    main()
