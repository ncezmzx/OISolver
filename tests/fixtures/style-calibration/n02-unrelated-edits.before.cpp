#include <bits/stdc++.h>
using namespace std;
const int INF = 1000000000;
int solve(vector<int>& a) {
    int ans = 0;
    for (int x : a) ans = max(ans, x);
    return ans;
}
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    vector<int> a = {1, 2, 3};
    cout << solve(a) << '\n';
}
