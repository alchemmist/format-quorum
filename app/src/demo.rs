use std::collections::HashMap;

#[derive(Debug,Clone)]
struct Point{x:f64,y:f64}
impl Point{fn dist(&self,o:&Point)->f64{((self.x-o.x).powi(2)+(self.y-o.y).powi(2)).sqrt()}}

enum Shape{Circle(f64),Rect{w:f64,h:f64}}
fn area(s:&Shape)->f64{match s{Shape::Circle(r)=>std::f64::consts::PI*r*r,Shape::Rect{w,h}=>w*h}}

fn main(){
let pts=vec![Point{x:0.0,y:0.0},Point{x:3.0,y:4.0}];
let mut counts:HashMap<String,i32>=HashMap::new();
for (i,p) in pts.iter().enumerate(){counts.insert(format!("p{}",i),p.x as i32);}
let total:f64=pts.windows(2).map(|w|w[0].dist(&w[1])).sum();
println!("total={} area={} counts={:?}",total,area(&Shape::Circle(2.0)),counts);
}
