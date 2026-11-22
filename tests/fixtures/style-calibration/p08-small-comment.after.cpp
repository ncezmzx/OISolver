#include <bits/stdc++.h>
using namespace std;

long long sum_to(long long n) {
    // Include n itself in the arithmetic-series sum.
    return n * (n + 1) / 2;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    long long n;
    cin >> n;
    cout << sum_to(n) << '\n';
}
