#include<bits/stdc++.h>
using namespace std;
#define int long long
int a[100005];
signed main(){
    ios::sync_with_stdio(false);cin.tie(nullptr);
    int n;cin>>n;
    int ans=0;
    for(int i=0;i<n-1;i++){cin>>a[i];ans+=a[i];}
    cout<<ans<<'\n';
}
