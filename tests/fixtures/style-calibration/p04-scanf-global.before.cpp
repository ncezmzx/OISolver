#include <cstdio>
const int N = 200005;
int a[N];
int main() {
    int n;
    scanf("%d", &n);
    for (int i = 1; i < n; ++i) scanf("%d", &a[i]);
    printf("%d\n", a[n]);
}
