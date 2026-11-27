// Geometry remains in Python; this accelerates only the same discrete search.
using System;
using System.IO;
using System.Collections.Generic;
class GridSearch {
    struct Entry { public int Id; public double G,F; public Entry(int id,double g,double f){Id=id;G=g;F=f;} }
    class Heap {
        List<Entry> a=new List<Entry>(); public int Count {get{return a.Count;}}
        public void Push(Entry v){a.Add(v);int i=a.Count-1;while(i>0){int p=(i-1)/2;if(a[p].F<=v.F)break;a[i]=a[p];i=p;}a[i]=v;}
        public Entry Pop(){Entry r=a[0],v=a[a.Count-1];a.RemoveAt(a.Count-1);if(a.Count>0){int i=0;while(i*2+1<a.Count){int c=i*2+1;if(c+1<a.Count&&a[c+1].F<a[c].F)c++;if(a[c].F>=v.F)break;a[i]=a[c];i=c;}a[i]=v;}return r;}
    }
    static int Main(string[] args){
        using(BinaryReader r=new BinaryReader(File.OpenRead(args[0]))){
            int nx=r.ReadInt32(),ny=r.ReadInt32(),nl=r.ReadInt32(),sx=r.ReadInt32(),sy=r.ReadInt32(),gx=r.ReadInt32(),gy=r.ReadInt32();
            double viaCost=r.ReadDouble(),ripCost=r.ReadDouble(); int n=nx*ny*nl,plane=nx*ny;
            int ns=r.ReadInt32();int[] sources=new int[ns];for(int i=0;i<ns;i++)sources[i]=r.ReadInt32();
            int ng=r.ReadInt32();bool[] goals=new bool[n];for(int i=0;i<ng;i++)goals[r.ReadInt32()]=true;
            byte[] blocked=r.ReadBytes(n),vias=r.ReadBytes(plane),reuse=r.ReadBytes(plane),rip=r.ReadBytes(n);
            double[] costs=new double[n];int[] parent=new int[n];for(int i=0;i<n;i++){costs[i]=double.PositiveInfinity;parent[i]=-1;}
            Heap h=new Heap();foreach(int l in sources){int id=l*plane+sy*nx+sx;if(blocked[id]==0){costs[id]=0;h.Push(new Entry(id,0,Math.Sqrt((sx-gx)*(sx-gx)+(sy-gy)*(sy-gy))));}}
            int found=-1,visited=0;int[] dx={1,-1,0,0,1,-1,1,-1},dy={0,0,1,-1,1,1,-1,-1};
            while(h.Count>0){Entry e=h.Pop();if(e.G!=costs[e.Id])continue;visited++;int li=e.Id/plane,local=e.Id%plane,x=local%nx,y=local/nx;if(goals[e.Id]){found=e.Id;break;}
                for(int q=0;q<8+nl;q++){
                    int xx=x,yy=y,ll=li;double add=0;
                    if(q<8){xx+=dx[q];yy+=dy[q];if(xx<0||xx>=nx||yy<0||yy>=ny)continue;if(dx[q]!=0&&dy[q]!=0&&(blocked[li*plane+y*nx+xx]!=0||blocked[li*plane+yy*nx+x]!=0))continue;add=dx[q]!=0&&dy[q]!=0?Math.Sqrt(2):1;}
                    else {ll=q-8;if(ll==li||(reuse[local]==0&&vias[local]!=0))continue;add=reuse[local]!=0?5:viaCost;}
                    int id=ll*plane+yy*nx+xx;if(blocked[id]!=0)continue;double cost=e.G+add+(rip[id]!=0?ripCost:0);
                    if(cost<costs[id]){costs[id]=cost;parent[id]=e.Id;double heur=Math.Sqrt((xx-gx)*(xx-gx)+(yy-gy)*(yy-gy));h.Push(new Entry(id,cost,cost+heur));}
                }
            }
            List<int> path=new List<int>();for(int id=found;id>=0;id=parent[id])path.Add(id);path.Reverse();
            using(BinaryWriter w=new BinaryWriter(File.Create(args[1]))){w.Write(visited);w.Write(path.Count);foreach(int id in path)w.Write(id);for(int id=0;id<n;id++)w.Write((byte)(double.IsPositiveInfinity(costs[id])?0:1));}
        }return 0;
    }
}
