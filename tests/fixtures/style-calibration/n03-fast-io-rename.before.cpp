#include <bits/stdc++.h>
using namespace std;
vector<int> values;
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n; cin >> n;
    values.resize(n);
    for (int i = 0; i < n; ++i) cin >> values[i];
    cout << *max_element(values.begin(), values.end());
}
