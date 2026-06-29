type ID = string | number
interface User{id:ID;name:string;roles?:string[]}
enum Status{Active,Inactive}

function pick<T,K extends keyof T>(o:T,k:K):T[K]{return o[k]}
const users:User[]=[{id:1,name:"ann"},{id:"x7",name:"bob",roles:["admin","ops"]}]
const byId=(id:ID):User|undefined=>users.find(u=>u.id===id)

class Repo<T>{
private items:T[]=[]
add(x:T):void{this.items.push(x)}
get all():readonly T[]{return this.items}
}

const repo=new Repo<User>()
users.forEach(u=>repo.add(u))
export {Status,pick,byId,repo}
