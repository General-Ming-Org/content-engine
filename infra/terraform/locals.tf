# URL helpers — production serves HTTPS via nginx on 443 at domain_name.

locals {
  public_url = var.domain_name != "" ? "https://${var.domain_name}" : ""
}
