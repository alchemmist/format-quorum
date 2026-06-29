const greet = (name) => `Hello, ${name}!`
class Counter{constructor(start=0){this.n=start}inc(){return ++this.n}get value(){return this.n}}
const nums=[1,2,3,4,5,6].filter(x=>x%2===0).map(x=>x*x).reduce((a,b)=>a+b,0)
const obj={a:1,b:2,nested:{c:3,d:[4,5,6]}}
async function load(url){const r=await fetch(url);if(!r.ok)throw new Error("bad");return r.json()}
function fib(n){return n<2?n:fib(n-1)+fib(n-2)}
const {a,...rest}=obj
for(const [k,v] of Object.entries(rest)){console.log(k,v)}
export {greet,Counter,fib,load,nums}
