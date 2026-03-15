import { useState } from "react";
import { motion } from "framer-motion";
import { 
  User, 
  Mail, 
  Lock, 
  Shield, 
  Save, 
  Eye, 
  EyeOff,
  AlertCircle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";

interface AdminSettingsProps {
  adminInfo: any;
  onUpdate: (updatedInfo: any) => void;
}

const AdminSettings = ({ adminInfo, onUpdate }: AdminSettingsProps) => {
  const [formData, setFormData] = useState({
    username: adminInfo?.username || "",
    full_name: adminInfo?.full_name || "",
    email: adminInfo?.email || "",
    current_password: "",
    new_password: "",
    confirm_password: ""
  });
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const handleChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      // Validate password change
      if (formData.new_password && formData.new_password !== formData.confirm_password) {
        toast({
          title: "Password Mismatch",
          description: "New password and confirm password do not match.",
          variant: "destructive"
        });
        return;
      }

      if (formData.new_password && !formData.current_password) {
        toast({
          title: "Current Password Required",
          description: "Please enter your current password to change it.",
          variant: "destructive"
        });
        return;
      }

      const token = localStorage.getItem("admin_token");
      const updateData: any = {};

      // Only include fields that have changed
      if (formData.username !== adminInfo?.username) {
        updateData.username = formData.username;
      }
      if (formData.full_name !== adminInfo?.full_name) {
        updateData.full_name = formData.full_name;
      }
      if (formData.email !== adminInfo?.email) {
        updateData.email = formData.email;
      }
      if (formData.new_password && formData.current_password) {
        updateData.current_password = formData.current_password;
        updateData.new_password = formData.new_password;
      }

      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/admin/me`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify(updateData)
      });

      if (response.ok) {
        const updatedAdmin = await response.json();
        onUpdate(updatedAdmin);
        
        // Reset password fields
        setFormData(prev => ({
          ...prev,
          current_password: "",
          new_password: "",
          confirm_password: ""
        }));

        toast({
          title: "Settings Updated",
          description: "Your admin information has been updated successfully.",
        });
      } else {
        const errorData = await response.json();
        toast({
          title: "Update Failed",
          description: errorData.detail || "Failed to update settings.",
          variant: "destructive"
        });
      }
    } catch (error) {
      toast({
        title: "Update Failed",
        description: "Network error. Please try again.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div>
        <h2 className="text-3xl font-bold">Admin Settings</h2>
        <p className="text-muted-foreground">Manage your account information and security</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Account Information
          </CardTitle>
          <CardDescription>
            Update your personal information and account details
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Basic Information */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <div className="relative">
                  <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="username"
                    type="text"
                    placeholder="Enter username"
                    value={formData.username}
                    onChange={(e) => handleChange("username", e.target.value)}
                    className="pl-10"
                    required
                    disabled={isLoading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name</Label>
                <div className="relative">
                  <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="full_name"
                    type="text"
                    placeholder="Enter full name"
                    value={formData.full_name}
                    onChange={(e) => handleChange("full_name", e.target.value)}
                    className="pl-10"
                    disabled={isLoading}
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  placeholder="Enter email address"
                  value={formData.email}
                  onChange={(e) => handleChange("email", e.target.value)}
                  className="pl-10"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Password Change Section */}
            <div className="border-t pt-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Lock className="h-5 w-5" />
                Change Password
              </h3>
              
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="current_password">Current Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="current_password"
                      type={showCurrentPassword ? "text" : "password"}
                      placeholder="Enter current password"
                      value={formData.current_password}
                      onChange={(e) => handleChange("current_password", e.target.value)}
                      className="pl-10 pr-10"
                      disabled={isLoading}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                      onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                      disabled={isLoading}
                    >
                      {showCurrentPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="new_password">New Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="new_password"
                        type={showNewPassword ? "text" : "password"}
                        placeholder="Enter new password"
                        value={formData.new_password}
                        onChange={(e) => handleChange("new_password", e.target.value)}
                        className="pl-10 pr-10"
                        disabled={isLoading}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        disabled={isLoading}
                      >
                        {showNewPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="confirm_password">Confirm New Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="confirm_password"
                        type={showConfirmPassword ? "text" : "password"}
                        placeholder="Confirm new password"
                        value={formData.confirm_password}
                        onChange={(e) => handleChange("confirm_password", e.target.value)}
                        className="pl-10 pr-10"
                        disabled={isLoading}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        disabled={isLoading}
                      >
                        {showConfirmPassword ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={isLoading}
                className="flex items-center gap-2"
              >
                {isLoading ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"></div>
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {isLoading ? "Updating..." : "Update Settings"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </motion.div>
  );
};

export default AdminSettings; 
