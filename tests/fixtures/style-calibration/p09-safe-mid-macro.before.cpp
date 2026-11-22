#include<bits/stdc++.h>
using namespace std;
#define int long long
int a[200005];
int find_pos(int l,int r,int x){while(l<r){int mid=(l+r)/2;if(a[mid]>=x)r=mid;else l=mid+1;}return l;}
signed main(){ios::sync_with_stdio(false);cin.tie(nullptr);int n,x;cin>>n>>x;for(int i=1;i<=n;i++)cin>>a[i];cout<<find_pos(1,n,x);}
