package demo;

import java.util.*;

public class Demo{
private final List<String> items=new ArrayList<>();
public Demo(String... xs){for(String x:xs){items.add(x);}}
public int total(){int s=0;for(String x:items){s+=x.length();}return s;}
public Map<String,Integer> lengths(){
Map<String,Integer> m=new HashMap<>();
for(String x:items){m.put(x,x.length());}
return m;
}
public static void main(String[] args){
Demo d=new Demo("a","bb","ccc");
System.out.println("total="+d.total()+" lengths="+d.lengths());
}
}
