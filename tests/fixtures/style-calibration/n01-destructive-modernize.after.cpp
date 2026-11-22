#include <bits/stdc++.h>
using namespace std;
int main() {
  int count;
  cin >> count;
  vector<long long> values(count);
  for (int index = 0; index < count; ++index) cin >> values[index];
  cout << values.front();
}
