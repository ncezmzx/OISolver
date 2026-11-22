#include <bits/stdc++.h>
using namespace std;
vector<int> nums;
int main() {
    int count; cin >> count;
    nums.resize(count);
    for (int index = 0; index < count; ++index) cin >> nums[index];
    sort(nums.begin(), nums.end());
    cout << nums.back();
}
