#include<bits/stdc++.h>
using namespace std;
#define int long long
int a[100005];
signed main(){ios::sync_with_stdio(false);cin.tie(nullptr);int n;cin>>n;vector<int>d;for(int i=1;i<=n;i++){cin>>a[i];auto p=upper_bound(d.begin(),d.end(),a[i]);if(p==d.end())d.push_back(a[i]);else *p=a[i];}cout<<d.size();}
