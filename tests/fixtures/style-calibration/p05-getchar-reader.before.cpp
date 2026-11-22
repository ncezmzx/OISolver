#include <bits/stdc++.h>
using namespace std;
int read(){int x=0,sign=0,c=getchar();while(c<'0'||c>'9'){if(c=='-')sign=-1;c=getchar();}while(c>='0'&&c<='9'){x=x*10+c-'0';c=getchar();}return x*sign;}
int main(){printf("%d\n",read());}
