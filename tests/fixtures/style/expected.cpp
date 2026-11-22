#include<bits/stdc++.h>
using namespace std;
#define int long long

int solve(vector<int> &a){
    vector<int> f;
    for(auto x:a){
        int p=lower_bound(f.begin(),f.end(),x)-f.begin();
        if(p==(int)f.size()) f.push_back(x);
        else f[p]=x;
    }
    return f.size();
}

signed main(){
    ios::sync_with_stdio(false);cin.tie(nullptr);
    int n;cin>>n;
    vector<int> a(n);
    for(auto &x:a) cin>>x;
    cout<<solve(a)<<'\n';
}
