#include <bits/stdc++.h>
using namespace std;
long long pref[100005];
long long query(int l, int r) {
    return pref[r] - pref[l];
}
int main(){int l,r;cin>>l>>r;cout<<query(l,r);}
