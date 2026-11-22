#include<bits/stdc++.h>
using namespace std;
vector<int> g[200005];
int main(){ios::sync_with_stdio(false);cin.tie(nullptr);int n;cin>>n;for(int i=1,u,v;i<n;i++){cin>>u>>v;g[u].push_back(v);g[v].push_back(u);}cout<<g[1].size();}
